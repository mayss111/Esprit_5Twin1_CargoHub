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
    from apps.tenders.forms import EXPEDITION_INDISPONIBLE, AppelOffreForm

    expedition.articles.all().delete()
    appel_offre.delete()  # l'expédition redevient disponible pour un appel
    date = (expedition.date_souhaitee - timedelta(days=1)).strftime("%Y-%m-%dT18:00")
    form = AppelOffreForm({"expedition": expedition.pk, "date_cloture": date, "prix_max": "150"}, pme=pme)
    assert form.errors["expedition"] == [EXPEDITION_INDISPONIBLE]


# ---------------------------------------------------------------- 5. formulaire « Nouvel appel d'offres »


def _rendre(expedition, cas, trajet, autre_pme):
    """Met l'expédition dans la situation `cas` (qui doit l'exclure du formulaire)."""
    from apps.bookings import services
    from apps.shipments.models import Expedition

    maj = Expedition.objects.filter(pk=expedition.pk).update
    if cas == "brouillon":
        maj(statut=Expedition.Statut.BROUILLON)
    elif cas == "0_kg":
        expedition.articles.all().delete()
    elif cas == "part_aujourd_hui":
        maj(date_souhaitee=timezone.localdate())
    elif cas == "date_passee":
        maj(date_souhaitee=timezone.localdate() - timedelta(days=1))
    elif cas == "appel_existant":
        AppelOffre.objects.create(expedition=expedition, date_cloture=timezone.now() + timedelta(hours=5))
    elif cas == "autre_pme":
        maj(pme=autre_pme)
    else:  # réservation EN_ATTENTE, ACCEPTEE ou EN_TRANSIT
        reservation = services.reserver(expedition, trajet)
        for statut in {"en_attente": [], "acceptee": ["ACCEPTEE"], "en_transit": ["ACCEPTEE", "EN_TRANSIT"]}[cas]:
            services.changer_statut(reservation, statut)


CAS_EXCLUS = [
    "brouillon",
    "0_kg",
    "part_aujourd_hui",
    "date_passee",
    "en_attente",
    "acceptee",
    "en_transit",
    "appel_existant",
    "autre_pme",
]


@pytest.mark.parametrize("cas", CAS_EXCLUS)
def test_expedition_exclue_du_formulaire(client, pme, autre_pme, expedition, trajet, cas):
    from apps.tenders.forms import EXPEDITION_INDISPONIBLE, AppelOffreForm, expeditions_pour_appel

    assert list(expeditions_pour_appel(pme)) == [expedition]  # au départ : proposée
    _rendre(expedition, cas, trajet, autre_pme)
    assert not expeditions_pour_appel(pme).exists()

    # Identifiant forcé dans le POST : refusé côté serveur, aucun appel créé.
    date = (timezone.localtime() + timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M")
    form = AppelOffreForm({"expedition": expedition.pk, "date_cloture": date, "prix_max": "150"}, pme=pme)
    assert form.errors["expedition"] == [EXPEDITION_INDISPONIBLE]

    # ?expedition=<id> : pas pré-rempli, et la page explique pourquoi.
    client.force_login(pme)
    reponse = client.get(reverse("tenders:creer"), {"expedition": expedition.pk})
    assert "expedition" not in reponse.context["form"].initial
    html = reponse.content.decode()
    assert ("pas d’appel d’offres possible, car" in html) is (cas != "autre_pme")  # l'id d'un autre : silence
    assert "Aucune de vos expéditions ne peut" in html and reverse("shipments:creer") in html


def test_raison_affichee_et_preremplissage(client, pme, expedition, trajet, autre_pme):
    from apps.tenders.forms import AppelOffreForm, pourquoi_indisponible

    assert pourquoi_indisponible(expedition) is None
    client.force_login(pme)
    assert client.get(reverse("tenders:creer"), {"expedition": expedition.pk}).context["form"].initial == {
        "expedition": expedition.pk
    }
    assert client.get(reverse("tenders:creer"), {"expedition": "abc"}).context["form"].initial == {}
    _rendre(expedition, "en_attente", trajet, autre_pme)
    assert pourquoi_indisponible(expedition) == "elle a déjà une réservation en cours"

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


def test_notes_des_avis_envoyees_au_llm(
    settings, pme, autre_pme, appel_offre, offre, trajet, autre_transporteur, autre_trajet
):
    import json as json_

    from apps.bookings import services
    from apps.tenders.ai import SANS_AVIS, recommander_offre
    from apps.tracking.models import Avis

    Trajet.objects.filter(pk=autre_trajet.pk).update(ville_depart="Monastir")  # offre compatible
    concurrente = Offre.objects.create(
        appel=appel_offre, transporteur=autre_transporteur, trajet=autre_trajet, prix=Decimal("120")
    )
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


# ---------------------------------------------------------------- 7. site toujours en français


def test_messages_en_francais_meme_si_le_navigateur_est_en_anglais(client, pme, expedition, appel_offre):
    appel_offre.delete()
    client.force_login(pme)
    reponse = client.post(reverse("tenders:creer"), {}, HTTP_ACCEPT_LANGUAGE="en-US,en;q=0.9")
    html = reponse.content.decode()
    assert "Ce champ est obligatoire" in html and "This field is required" not in html


# ---------------------------------------------------------------- 8. données de démo de la soutenance


def test_donnees_demo_soutenance_idempotentes(db):
    from apps.accounts.models import Utilisateur
    from apps.tenders.ai import resumer_offres
    from apps.tracking.models import Avis

    sortie = StringIO()
    call_command("donnees_demo", stdout=sortie)
    call_command("donnees_demo", stdout=sortie)  # relancée : aucun doublon
    assert "Scénario de soutenance prêt" in sortie.getvalue()

    mohamed = Utilisateur.objects.get(email="mohamed@transport.tn")
    assert mohamed.is_active and mohamed.check_password("cargohub2026")
    appel = AppelOffre.objects.get(expedition__description="[démo soutenance]")
    assert appel.statut == AppelOffre.Statut.OUVERT and appel.est_ouvert
    assert appel.expedition.poids_total_kg == 300
    offres = {o.transporteur.first_name: o for o in appel.offres.select_related("transporteur", "trajet")}
    assert set(offres) == {"Karim", "Mohamed"} and offres["Mohamed"].prix < offres["Karim"].prix
    for offre in offres.values():
        assert est_compatible(appel.expedition, offre.trajet)  # les deux offres sont « retenables »
    assert [e.ville for e in offres["Karim"].trajet.etapes.all()] == ["Monastir", "Sousse"]
    # Mohamed : 1 trajet pour l’offre + 2 transports passés (ses avis) ; 5 avis au total — rien en double.
    assert Trajet.objects.filter(transporteur=mohamed).count() == 3 and Avis.objects.count() == 5

    notes = {o["transporteur"]: o["note"] for o in resumer_offres(appel)}
    assert notes == {"Karim": 4.7, "Mohamed": 2.5}  # vrai arbitrage : Mohamed moins cher, Karim mieux noté


# ---------------------------------------------------------------- 3 (retest). offre devenue incompatible


@pytest.fixture
def offre_incompatible(appel_offre, autre_transporteur, autre_trajet):
    """Nabil propose un trajet Sousse → Tunis : il ne passe pas par Monastir (cas de l'appel #62)."""
    return Offre.objects.create(
        appel=appel_offre, transporteur=autre_transporteur, trajet=autre_trajet, prix=Decimal("70")
    )


def test_badge_trajet_incompatible_a_la_place_de_retenir(client, pme, appel_offre, offre, offre_incompatible):
    client.force_login(pme)
    reponse = client.get(reverse("tenders:detail", args=[appel_offre.pk]))
    html = reponse.content.decode()
    assert reponse.context["incompatibles"] == {offre_incompatible.pk}
    assert "Trajet incompatible" in html
    assert reverse("tenders:retenir", args=[offre_incompatible.pk]) not in html
    assert reverse("tenders:retenir", args=[offre.pk]) in html  # l'offre compatible garde son bouton


def test_retenir_une_offre_incompatible_par_la_page(client, pme, appel_offre, offre_incompatible):
    client.force_login(pme)
    reponse = client.post(reverse("tenders:retenir", args=[offre_incompatible.pk]), follow=True)
    assert "ne correspond plus à l’expédition" in reponse.content.decode()
    assert not Reservation.objects.exists()
    offre_incompatible.refresh_from_db()
    assert offre_incompatible.statut == Offre.Statut.PROPOSEE


def test_aide_au_choix_ignore_les_offres_incompatibles(settings, appel_offre, offre, offre_incompatible):
    import json as json_

    from apps.tenders.ai import recommander_offre, resumer_offres

    assert [o["offre_id"] for o in resumer_offres(appel_offre)] == [offre.pk]  # jamais envoyée au LLM

    settings.AI_API_KEY = "cle-de-test"
    reponse = json_.dumps({"offre_id": offre_incompatible.pk, "explication": "La moins chère."})
    with mock.patch("apps.core.ai.demander", return_value=reponse):
        resultat = recommander_offre(appel_offre)
    assert resultat["offre_id"] == offre.pk and resultat["methode"].startswith("règle")  # repli


def test_lancer_aide_au_choix_compte_seulement_les_offres_compatibles(
    client, pme, appel_offre, offre, offre_incompatible
):
    client.force_login(pme)
    reponse = client.post(reverse("tenders:recommander", args=[appel_offre.pk]), follow=True)
    assert "au moins 2 offres compatibles" in reponse.content.decode()
    appel_offre.refresh_from_db()
    assert appel_offre.recommandation_statut == ""


def test_donnees_demo_se_reparent(db):
    from apps.accounts.models import Utilisateur

    call_command("donnees_demo", stdout=StringIO())
    appel = AppelOffre.objects.get(expedition__description="[démo soutenance]")
    karim = appel.offres.get(transporteur__email="karim@transport.tn")
    # Ce qui a pu arriver en production pendant les essais :
    Vehicule.objects.filter(immatriculation="214 TU 3381").update(conforme=False)
    Utilisateur.objects.filter(email="mohamed@transport.tn").update(is_active=False)
    karim.trajet.etapes.create(ordre=3, ville="Hammamet")
    karim.trajet.etapes.filter(ordre=1).update(ville="Kairouan")

    sortie = StringIO()
    call_command("donnees_demo", stdout=sortie)
    texte = sortie.getvalue()
    assert texte.count("-> compatible") == 2 and "INCOMPATIBLE" not in texte
    assert "Sfax - Tunis, via Monastir, Sousse, score 100/100, note 4.7/5" in texte
    assert Utilisateur.objects.get(email="mohamed@transport.tn").is_active
    karim.trajet.refresh_from_db()
    assert [e.ville for e in karim.trajet.etapes.all()] == ["Monastir", "Sousse"]
    assert est_compatible(appel.expedition, karim.trajet)
