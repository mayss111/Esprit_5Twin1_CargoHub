"""Tests des corrections issues des essais en production (M4)."""

from datetime import timedelta
from decimal import Decimal
from io import StringIO
from unittest import mock

import pytest
from django.apps import apps
from django.core.management import call_command
from django.urls import reverse
from django.utils import timezone

from apps.bookings.models import Reservation
from apps.bookings.services import ReservationImpossible, est_compatible
from apps.core import ai
from apps.fleet.models import Trajet, Vehicule
from apps.tenders import apps as config_tenders
from apps.tenders.ai import chauffer_modele
from apps.tenders.forms import TRAJET_INCOMPATIBLE, OffreForm
from apps.tenders.models import AppelOffre, Offre
from apps.tenders.services import retenir_offre


@pytest.fixture
def offre(appel_offre, transporteur, trajet):
    return Offre.objects.create(appel=appel_offre, transporteur=transporteur, trajet=trajet, prix=Decimal("90"))


@pytest.fixture
def trajet_tardif(trajet):
    """Bon itinéraire et assez de place (score 70), mais 6 jours après la date souhaitée : le cas vu en production."""
    return Trajet.objects.create(
        transporteur=trajet.transporteur,
        vehicule=trajet.vehicule,
        ville_depart="Monastir",
        ville_arrivee="Tunis",
        date_depart=trajet.date_depart + timedelta(days=6),
        capacite_dispo_kg=Decimal("1000"),
        capacite_dispo_m3=Decimal("8"),
        distance_km=160,
    )


# ---------------------------------------------------------------- 1. préchargement de scikit-learn et chauffe


@pytest.mark.parametrize(
    "argv, attendu",
    [
        (["manage.py", "migrate"], False),
        (["manage.py", "collectstatic", "--noinput"], False),
        (["manage.py", "runserver"], True),
        (["/usr/local/bin/daphne", "config.asgi:application"], True),
        (["/usr/local/bin/celery", "-A", "config", "worker"], True),
    ],
)
def test_quand_precharger(argv, attendu):
    assert config_tenders.doit_prechauffer(argv, en_test=False) is attendu


def test_pas_de_prechargement_pendant_les_tests():
    assert config_tenders.doit_prechauffer() is False


def test_chauffe_du_modele():
    modele = chauffer_modele()
    assert modele.predict([[150.0, 1500.0, 225.0]])[0] > 0


def test_ready_ne_bloque_jamais_le_demarrage():
    config = apps.get_app_config("tenders")
    with (
        mock.patch.object(config_tenders, "doit_prechauffer", return_value=True),
        mock.patch("apps.tenders.ai.chauffer_modele", side_effect=ImportError("scikit-learn absent")) as chauffe,
    ):
        config.ready()  # aucune exception
    chauffe.assert_called_once()


def test_chauffer_ia_sans_cle(db):
    sortie = StringIO()
    call_command("chauffer_ia", stdout=sortie)
    texte = sortie.getvalue()
    assert "Suggestion de prix :" in texte and " ms (formule" in texte and "pas de clé" in texte


def test_chauffer_ia_avec_llm(db, settings):
    settings.AI_API_KEY, settings.AI_MODEL = "cle-de-test", "modele-test"
    sortie = StringIO()
    with mock.patch("apps.core.ai.demander", return_value="OK"):
        call_command("chauffer_ia", stdout=sortie)
    assert "LLM (modele-test) :" in sortie.getvalue()
    with mock.patch("apps.core.ai.demander", side_effect=ai.IAIndisponible("modèle introuvable")):
        call_command("chauffer_ia", stdout=sortie)
    assert "indisponible : modèle introuvable" in sortie.getvalue()


# ---------------------------------------------------------------- 2. offre seulement sur un trajet compatible


def test_regle_de_compatibilite(expedition, trajet, trajet_tardif, autre_trajet):
    assert est_compatible(expedition, trajet)
    assert not est_compatible(expedition, trajet_tardif)  # bonnes villes, mais 6 jours trop tard
    assert not est_compatible(expedition, autre_trajet)  # ne passe pas par Monastir
    Vehicule.objects.filter(pk=trajet.vehicule_id).update(conforme=False)
    trajet.refresh_from_db()
    assert not est_compatible(expedition, trajet)


def test_formulaire_ne_propose_que_les_trajets_compatibles(appel_offre, transporteur, trajet, trajet_tardif):
    form = OffreForm(transporteur=transporteur, appel=appel_offre)
    assert list(form.fields["trajet"].queryset) == [trajet]
    form = OffreForm({"trajet": trajet_tardif.pk, "prix": "90"}, transporteur=transporteur, appel=appel_offre)
    assert form.errors["trajet"] == [TRAJET_INCOMPATIBLE]


def test_trajet_devenu_incompatible_pendant_la_saisie(appel_offre, transporteur, trajet):
    form = OffreForm({"trajet": trajet.pk, "prix": "90"}, transporteur=transporteur, appel=appel_offre)
    Trajet.objects.filter(pk=trajet.pk).update(date_depart=trajet.date_depart + timedelta(days=5))
    assert not form.is_valid() and form.errors["trajet"] == [TRAJET_INCOMPATIBLE]


def test_page_explique_l_absence_de_trajet_compatible(client, transporteur, appel_offre, trajet):
    Trajet.objects.filter(pk=trajet.pk).update(date_depart=trajet.date_depart + timedelta(days=6))
    client.force_login(transporteur)
    html = client.get(reverse("tenders:offre_creer", args=[appel_offre.pk])).content.decode()
    assert "Aucun de vos trajets ne convient" in html and "<strong>Monastir</strong>" in html
    assert 'id="form-offre"' not in html


def test_retenir_reverifie_le_trajet(pme, appel_offre, offre, trajet):
    Trajet.objects.filter(pk=trajet.pk).update(date_depart=trajet.date_depart + timedelta(days=5))
    with pytest.raises(ReservationImpossible, match="ne correspond plus"):
        retenir_offre(offre, par=pme)
    appel_offre.refresh_from_db()
    assert appel_offre.statut == AppelOffre.Statut.OUVERT and not Reservation.objects.exists()


# ---------------------------------------------------------------- 4. expédition de 0 kg


def test_appel_d_offres_sur_une_expedition_vide(pme, expedition, appel_offre):
    from apps.bookings.services import EXPEDITION_VIDE
    from apps.tenders.forms import AppelOffreForm

    expedition.articles.all().delete()
    appel_offre.delete()  # l'expédition redevient disponible pour un appel
    expedition.refresh_from_db()
    date = (expedition.date_souhaitee - timedelta(days=1)).strftime("%Y-%m-%dT18:00")
    form = AppelOffreForm({"expedition": expedition.pk, "date_cloture": date, "prix_max": "150"}, pme=pme)
    assert form.errors["expedition"] == [EXPEDITION_VIDE]


# ---------------------------------------------------------------- 5. formulaire « Nouvel appel d'offres »


def test_expeditions_proposees_pour_un_appel(pme, expedition, trajet):
    from apps.bookings import services
    from apps.shipments.models import Expedition
    from apps.tenders.forms import AppelOffreForm, expeditions_pour_appel

    assert list(expeditions_pour_appel(pme)) == [expedition]
    reservation = services.reserver(expedition, trajet)
    assert list(expeditions_pour_appel(pme)) == [expedition]  # simple demande : toujours proposée
    services.changer_statut(reservation, Reservation.Statut.ACCEPTEE)
    assert not expeditions_pour_appel(pme).exists()  # un transporteur est déjà trouvé

    services.changer_statut(reservation, Reservation.Statut.ANNULEE)
    Expedition.objects.filter(pk=expedition.pk).update(date_souhaitee=timezone.localdate() - timedelta(days=1))
    assert not expeditions_pour_appel(pme).exists()  # date passée : aucune date limite possible
    Expedition.objects.filter(pk=expedition.pk).update(date_souhaitee=timezone.localdate())
    assert list(expeditions_pour_appel(pme)) == [expedition]

    attribut_min = AppelOffreForm(pme=pme).fields["date_cloture"].widget.attrs["min"]
    assert attribut_min.startswith(timezone.localtime().strftime("%Y-%m-%dT")) and len(attribut_min) == 16


def test_page_nouvel_appel_a_un_min(client, pme, expedition, appel_offre):
    client.force_login(pme)
    appel_offre.delete()
    html = client.get(reverse("tenders:creer")).content.decode()
    assert f'min="{timezone.localtime():%Y-%m-%d}' in html


# ---------------------------------------------------------------- 6. aide au choix : noms et notes des avis


@pytest.mark.parametrize(
    "texte, attendu",
    [
        (
            "Je recommande l'offre 63 car elle est moins chère.",
            "Je recommande l’offre de Karim car elle est moins chère.",
        ),
        ("L’offre n° 63 est la meilleure.", "L’offre de Karim est la meilleure."),
        ("La meilleure offre #63, devant offre_id 64.", "La meilleure offre de Karim, devant offre de Nabil."),
        ("L'offre 999 n'existe pas.", "L'offre 999 n'existe pas."),  # numéro inconnu : inchangé
    ],
)
def test_identifiants_remplaces_par_les_noms(texte, attendu):
    from apps.tenders.ai import sans_identifiants

    assert sans_identifiants(texte, {63: "Karim", 64: "Nabil"}) == attendu


def test_notes_des_avis_envoyees_au_llm(settings, pme, autre_pme, appel_offre, offre, trajet, autre_transporteur):
    import json as json_

    from apps.bookings import services
    from apps.tenders.ai import SANS_AVIS, recommander_offre
    from apps.tracking.models import Avis

    concurrente = Offre.objects.create(appel=appel_offre, transporteur=autre_transporteur, prix=Decimal("120"))
    passee = services.reserver(appel_offre.expedition, trajet)
    Avis.objects.create(reservation=passee, auteur=pme, cible=offre.transporteur, note=4)
    Avis.objects.create(reservation=passee, auteur=autre_pme, cible=offre.transporteur, note=5)

    settings.AI_API_KEY = "cle-de-test"
    reponse = json_.dumps({"offre_id": offre.pk, "explication": f"L'offre {offre.pk} est la mieux notée."})
    with mock.patch("apps.core.ai.demander", return_value=reponse) as llm:
        resultat = recommander_offre(appel_offre)

    envoye = llm.call_args.args[0]
    assert '"note": 4.5' in envoye and f'"note": "{SANS_AVIS}"' in envoye
    assert '"transporteur": "Karim"' in envoye and '"transporteur": "Nabil"' in envoye
    assert "nom de son transporteur" in llm.call_args.kwargs["systeme"]
    assert resultat["explication"] == "L’offre de Karim est la mieux notée."
    assert str(offre.pk) not in resultat["explication"] and concurrente.pk != offre.pk
