"""Tests du module Appels d’offres & négociation (M4) : règles, retenir une offre, IA, pages par rôle, back-office."""

import json
from datetime import timedelta
from decimal import Decimal
from io import StringIO
from unittest import mock

import pytest
from django.core.management import call_command
from django.db import IntegrityError
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import ProfilTransporteur, Utilisateur
from apps.bookings.models import Notification, Reservation
from apps.bookings.services import ReservationImpossible
from apps.core.roles import Role
from apps.fleet.models import Trajet, Vehicule
from apps.tenders.ai import recommander_depuis_resume, recommander_par_regle, suggerer_prix
from apps.tenders.forms import AppelOffreForm, OffreForm
from apps.tenders.models import AppelOffre, Offre
from apps.tenders.services import retenir_offre
from apps.tenders.tasks import calculer_recommandation, cloturer_appels_offres


@pytest.fixture
def offre(appel_offre, transporteur, trajet):
    return Offre.objects.create(appel=appel_offre, transporteur=transporteur, trajet=trajet, prix=Decimal("90"))


@pytest.fixture
def offre_concurrente(appel_offre, autre_transporteur, autre_trajet):
    return Offre.objects.create(
        appel=appel_offre, transporteur=autre_transporteur, trajet=autre_trajet, prix=Decimal("120")
    )


def _dans(jours):
    return (timezone.now() + timedelta(days=jours)).strftime("%Y-%m-%dT%H:%M")


def _refresh(*objets):
    for o in objets:
        o.refresh_from_db()


# ---------------------------------------------------------------- règles des modèles et formulaires


def test_appel_ouvert_et_modifiable(appel_offre, offre):
    assert appel_offre.est_ouvert and not appel_offre.modifiable  # une offre reçue : plus modifiable
    assert offre.modifiable and str(offre).endswith("90 DT")
    appel_offre.date_cloture = timezone.now() - timedelta(minutes=1)
    assert not appel_offre.est_ouvert and not offre.modifiable


def test_une_seule_offre_par_transporteur_en_base(offre, appel_offre, transporteur):
    with pytest.raises(IntegrityError):
        Offre.objects.create(appel=appel_offre, transporteur=transporteur, prix=Decimal("80"))


@pytest.mark.parametrize(
    "donnees, champ",
    [
        ({"date_cloture": _dans(-1), "prix_max": "150"}, "date_cloture"),  # date passée
        ({"date_cloture": _dans(10), "prix_max": "150"}, "date_cloture"),  # après la date d'expédition
        ({"date_cloture": _dans(1), "prix_max": "0"}, "prix_max"),
        ({"date_cloture": _dans(1), "prix_max": ""}, "prix_max"),
    ],
)
def test_formulaire_appel_invalide(pme, expedition, donnees, champ):
    form = AppelOffreForm({"expedition": expedition.pk, **donnees}, pme=pme)
    assert not form.is_valid() and champ in form.errors


def test_formulaire_appel_valide_et_expeditions_proposees(pme, autre_pme, expedition):
    form = AppelOffreForm({"expedition": expedition.pk, "date_cloture": _dans(1), "prix_max": "150"}, pme=pme)
    assert form.is_valid(), form.errors
    assert not AppelOffreForm(pme=autre_pme).fields["expedition"].queryset.exists()  # pas les expéditions des autres


def test_formulaire_offre(appel_offre, transporteur, trajet, autre_trajet, offre):
    form = OffreForm({"trajet": trajet.pk, "prix": "95"}, transporteur=transporteur, appel=appel_offre)
    assert not form.is_valid() and "déjà fait une offre" in str(form.errors)
    form = OffreForm({"trajet": autre_trajet.pk, "prix": "95"}, transporteur=transporteur, appel=appel_offre)
    assert "trajet" in form.errors  # le trajet d'un autre transporteur n'est pas proposé
    form = OffreForm({"trajet": trajet.pk, "prix": "0"}, instance=offre, transporteur=transporteur, appel=appel_offre)
    assert "prix" in form.errors


def test_formulaire_offre_appel_clos(appel_offre, transporteur, trajet):
    AppelOffre.objects.filter(pk=appel_offre.pk).update(statut=AppelOffre.Statut.CLOTURE)
    appel_offre.refresh_from_db()
    form = OffreForm({"trajet": trajet.pk, "prix": "95"}, transporteur=transporteur, appel=appel_offre)
    assert not form.is_valid() and "clos" in str(form.errors)


def test_tache_celery_cloture_les_appels_expires(appel_offre):
    AppelOffre.objects.filter(pk=appel_offre.pk).update(date_cloture=timezone.now() - timedelta(hours=1))
    assert cloturer_appels_offres() == 1
    appel_offre.refresh_from_db()
    assert appel_offre.statut == AppelOffre.Statut.CLOTURE


# ---------------------------------------------------------------- retenir une offre (logique métier)


def test_retenir_une_offre(pme, appel_offre, offre, offre_concurrente, trajet, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):  # la notification part après le COMMIT
        reservation = retenir_offre(offre, par=pme)
    _refresh(appel_offre, offre, offre_concurrente, trajet)
    assert offre.statut == Offre.Statut.RETENUE and offre_concurrente.statut == Offre.Statut.REJETEE
    assert appel_offre.statut == AppelOffre.Statut.ATTRIBUE
    assert reservation.statut == Reservation.Statut.ACCEPTEE and reservation.prix_convenu == Decimal("90")
    assert trajet.capacite_dispo_kg == Decimal("700")  # 300 kg retirés du camion
    assert Notification.objects.filter(destinataire=offre.transporteur, titre="Votre offre a été retenue").exists()


def test_retenir_sans_place_n_applique_rien(pme, appel_offre, offre, offre_concurrente, trajet):
    Trajet.objects.filter(pk=trajet.pk).update(capacite_dispo_kg=Decimal("50"))
    with pytest.raises(ReservationImpossible):
        retenir_offre(offre, par=pme)
    _refresh(appel_offre, offre, offre_concurrente)
    assert appel_offre.statut == AppelOffre.Statut.OUVERT  # transaction annulée : rien n'a changé
    assert offre.statut == offre_concurrente.statut == Offre.Statut.PROPOSEE
    assert not Reservation.objects.exists()


def test_retenir_cas_impossibles(pme, appel_offre, offre):
    Offre.objects.filter(pk=offre.pk).update(trajet=None)
    with pytest.raises(ReservationImpossible, match="trajet"):
        retenir_offre(offre, par=pme)
    Offre.objects.filter(pk=offre.pk).update(statut=Offre.Statut.REJETEE)
    with pytest.raises(ReservationImpossible, match="plus disponible"):
        retenir_offre(offre, par=pme)
    AppelOffre.objects.filter(pk=appel_offre.pk).update(statut=AppelOffre.Statut.ANNULE)
    with pytest.raises(ReservationImpossible, match="plus ouvert"):
        retenir_offre(offre, par=pme)


# ---------------------------------------------------------------- IA : suggestion de prix et historique de démo


def test_suggestion_formule_sans_historique(db):
    resultat = suggerer_prix(distance_km=160, poids_kg=300)
    assert resultat["methode"] == "formule" and resultat["prix"] >= 30


def test_generer_offres_demo_idempotent_et_regression(db):
    sortie = StringIO()
    call_command("generer_offres_demo", stdout=sortie)
    call_command("generer_offres_demo", stdout=sortie)
    assert Offre.objects.filter(statut=Offre.Statut.RETENUE).count() == 60
    assert "rien à faire" in sortie.getvalue()
    resultat = suggerer_prix(distance_km=270, poids_kg=2000)
    assert resultat["methode"] == "régression sur 60 offres"
    attendu = 25 + 0.32 * 270 * 2 + 0.04 * 270  # logique utilisée pour générer l'historique
    assert abs(float(resultat["prix"]) - attendu) < 15


def test_suggestion_prix_json(client, transporteur, appel_offre, trajet):
    client.force_login(transporteur)
    url = reverse("tenders:suggestion_prix")
    assert client.get(url).status_code == 405
    reponse = client.post(url, {"appel": appel_offre.pk, "trajet": trajet.pk})
    data = reponse.json()
    assert reponse.status_code == 200 and set(data) == {"prix", "methode", "duree_ms"}
    assert Decimal(data["prix"]) >= 30 and data["methode"] == "formule" and data["duree_ms"] >= 0


def test_suggestion_prix_erreurs(client, transporteur, appel_offre, trajet, autre_trajet):
    client.force_login(transporteur)
    url = reverse("tenders:suggestion_prix")
    assert client.post(url, {"appel": appel_offre.pk}).status_code == 400
    assert client.post(url, {"appel": appel_offre.pk, "trajet": autre_trajet.pk}).status_code == 400  # pas son trajet
    Trajet.objects.filter(pk=trajet.pk).update(distance_km=None)
    reponse = client.post(url, {"appel": appel_offre.pk, "trajet": trajet.pk})
    assert reponse.status_code == 400 and "distance" in reponse.json()["erreur"]


def test_suggestion_prix_service_en_panne(client, transporteur, appel_offre, trajet):
    client.force_login(transporteur)
    with mock.patch("apps.tenders.views.suggerer_prix", side_effect=RuntimeError("scikit-learn absent")):
        reponse = client.post(reverse("tenders:suggestion_prix"), {"appel": appel_offre.pk, "trajet": trajet.pk})
    assert reponse.status_code == 503 and "indisponible" in reponse.json()["erreur"]


def test_suggestion_prix_reservee_aux_transporteurs(client, pme, appel_offre, trajet):
    client.force_login(pme)
    assert (
        client.post(reverse("tenders:suggestion_prix"), {"appel": appel_offre.pk, "trajet": trajet.pk}).status_code
        == 403
    )


# ---------------------------------------------------------------- PME : appels d'offres (intégration)


def test_liste_selon_le_role(client, pme, autre_pme, transporteur, appel_offre):
    client.force_login(pme)
    assert list(client.get(reverse("tenders:liste")).context["object_list"]) == [appel_offre]
    client.force_login(autre_pme)
    assert not client.get(reverse("tenders:liste")).context["object_list"]
    client.force_login(transporteur)
    assert list(client.get(reverse("tenders:liste")).context["object_list"]) == [appel_offre]
    AppelOffre.objects.filter(pk=appel_offre.pk).update(statut=AppelOffre.Statut.CLOTURE)
    assert not client.get(reverse("tenders:liste")).context["object_list"]  # clos et sans offre de sa part


def test_creer_un_appel(client, pme, expedition):
    client.force_login(pme)
    url = reverse("tenders:creer")
    assert client.get(url, {"expedition": expedition.pk}).context["form"].initial["expedition"] == expedition.pk
    reponse = client.post(url, {"expedition": expedition.pk, "date_cloture": _dans(-1), "prix_max": "150"})
    assert reponse.status_code == 200 and not AppelOffre.objects.exists()
    reponse = client.post(url, {"expedition": expedition.pk, "date_cloture": _dans(1), "prix_max": "150"})
    appel = AppelOffre.objects.get()
    assert reponse.url == reverse("tenders:detail", args=[appel.pk]) and appel.prix_max == Decimal("150")


def test_creer_sans_expedition_disponible(client, autre_pme):
    client.force_login(autre_pme)
    assert "Aucune de vos expéditions ne peut" in client.get(reverse("tenders:creer")).content.decode()


def test_modifier_et_supprimer_sans_offre(client, pme, appel_offre):
    client.force_login(pme)
    url = reverse("tenders:modifier", args=[appel_offre.pk])
    assert client.get(url).status_code == 200
    client.post(url, {"date_cloture": _dans(1), "prix_max": "180"})
    appel_offre.refresh_from_db()
    assert appel_offre.prix_max == Decimal("180")
    assert client.get(reverse("tenders:supprimer", args=[appel_offre.pk])).status_code == 200
    client.post(reverse("tenders:supprimer", args=[appel_offre.pk]))
    assert not AppelOffre.objects.exists()


def test_appel_avec_offres_non_modifiable(client, pme, appel_offre, offre):
    client.force_login(pme)
    reponse = client.post(
        reverse("tenders:modifier", args=[appel_offre.pk]), {"date_cloture": _dans(1), "prix_max": "1"}
    )
    assert reponse.url == reverse("tenders:detail", args=[appel_offre.pk])
    client.post(reverse("tenders:supprimer", args=[appel_offre.pk]))
    appel_offre.refresh_from_db()
    assert appel_offre.prix_max == Decimal("200")


@pytest.mark.parametrize("nom", ["modifier", "supprimer", "detail"])
def test_appel_d_une_autre_pme_introuvable(client, autre_pme, appel_offre, nom):
    client.force_login(autre_pme)
    assert client.get(reverse(f"tenders:{nom}", args=[appel_offre.pk])).status_code == 404


def test_creer_un_appel_interdit_au_transporteur(client, transporteur, appel_offre):
    client.force_login(transporteur)
    assert client.get(reverse("tenders:creer")).status_code == 403
    assert client.get(reverse("tenders:modifier", args=[appel_offre.pk])).status_code == 403


def test_detail_pour_la_pme(client, pme, appel_offre, offre, offre_concurrente):
    client.force_login(pme)
    reponse = client.get(reverse("tenders:detail", args=[appel_offre.pk]))
    assert list(reponse.context["offres"]) == [offre, offre_concurrente]  # moins chère d'abord
    assert reponse.context["prix_moyen"] == Decimal("105")
    assert "Retenir" in reponse.content.decode()


def test_retenir_par_la_page(client, pme, autre_pme, offre):
    client.force_login(autre_pme)
    assert client.post(reverse("tenders:retenir", args=[offre.pk])).status_code == 404
    client.force_login(pme)
    assert client.get(reverse("tenders:retenir", args=[offre.pk])).status_code == 405
    reponse = client.post(reverse("tenders:retenir", args=[offre.pk]))
    reservation = Reservation.objects.get()
    assert reponse.url == reverse("bookings:detail", args=[reservation.pk])


def test_retenir_par_la_page_sans_place(client, pme, offre, trajet):
    Trajet.objects.filter(pk=trajet.pk).update(capacite_dispo_kg=Decimal("10"))
    client.force_login(pme)
    reponse = client.post(reverse("tenders:retenir", args=[offre.pk]), follow=True)
    assert "n’a pas pu être retenue" in reponse.content.decode() and not Reservation.objects.exists()


# ---------------------------------------------------------------- transporteur : offres (intégration)


def test_faire_une_offre(client, transporteur, appel_offre, trajet):
    client.force_login(transporteur)
    detail = client.get(reverse("tenders:detail", args=[appel_offre.pk])).content.decode()
    assert "Faire une offre" in detail
    url = reverse("tenders:offre_creer", args=[appel_offre.pk])
    html = client.get(url).content.decode()
    assert "Suggérer un prix" in html and 'aria-live="polite"' in html
    reponse = client.post(url, {"trajet": trajet.pk, "prix": "95", "message": "Départ tôt le matin"})
    assert reponse.url == reverse("tenders:detail", args=[appel_offre.pk])
    offre = Offre.objects.get()
    assert (offre.transporteur, offre.prix) == (transporteur, Decimal("95"))
    assert client.get(url).url == reverse("tenders:offre_modifier", args=[offre.pk])  # pas de deuxième offre


def test_faire_une_offre_invalide_ou_sans_trajet(client, transporteur, autre_transporteur, appel_offre, trajet):
    client.force_login(transporteur)
    reponse = client.post(reverse("tenders:offre_creer", args=[appel_offre.pk]), {"trajet": trajet.pk, "prix": "-5"})
    assert reponse.status_code == 200 and not Offre.objects.exists()
    client.force_login(autre_transporteur)  # aucun trajet ouvert
    assert (
        "Créez d’abord un trajet" in client.get(reverse("tenders:offre_creer", args=[appel_offre.pk])).content.decode()
    )


def test_offre_sur_appel_clos(client, transporteur, appel_offre):
    AppelOffre.objects.filter(pk=appel_offre.pk).update(date_cloture=timezone.now() - timedelta(minutes=5))
    client.force_login(transporteur)
    assert client.get(reverse("tenders:offre_creer", args=[appel_offre.pk])).url == reverse("tenders:liste")


def test_offre_interdite_a_la_pme(client, pme, appel_offre):
    client.force_login(pme)
    assert client.get(reverse("tenders:offre_creer", args=[appel_offre.pk])).status_code == 403


def test_modifier_et_retirer_mon_offre(client, transporteur, offre, trajet):
    client.force_login(transporteur)
    detail = client.get(reverse("tenders:detail", args=[offre.appel_id]))
    assert detail.context["mon_offre"] == offre
    client.post(reverse("tenders:offre_modifier", args=[offre.pk]), {"trajet": trajet.pk, "prix": "88"})
    offre.refresh_from_db()
    assert offre.prix == Decimal("88")
    assert client.get(reverse("tenders:offre_retirer", args=[offre.pk])).status_code == 200
    client.post(reverse("tenders:offre_retirer", args=[offre.pk]))
    assert not Offre.objects.exists()


def test_offre_d_un_autre_transporteur(client, autre_transporteur, offre):
    client.force_login(autre_transporteur)
    for nom in ["offre_modifier", "offre_retirer"]:
        assert client.get(reverse(f"tenders:{nom}", args=[offre.pk])).status_code == 404


def test_offre_traitee_non_modifiable(client, transporteur, offre):
    Offre.objects.filter(pk=offre.pk).update(statut=Offre.Statut.REJETEE)
    client.force_login(transporteur)
    reponse = client.post(reverse("tenders:offre_retirer", args=[offre.pk]))
    assert reponse.url == reverse("tenders:detail", args=[offre.appel_id]) and Offre.objects.exists()


def test_appel_clos_visible_seulement_si_j_ai_fait_une_offre(client, transporteur, autre_transporteur, offre):
    AppelOffre.objects.filter(pk=offre.appel_id).update(statut=AppelOffre.Statut.CLOTURE)
    client.force_login(transporteur)
    assert client.get(reverse("tenders:detail", args=[offre.appel_id])).status_code == 200
    client.force_login(autre_transporteur)
    assert client.get(reverse("tenders:detail", args=[offre.appel_id])).status_code == 404


# ---------------------------------------------------------------- back-office


def test_backoffice_appels(client, admin_user, appel_offre, offre):
    client.force_login(admin_user)
    reponse = client.get(reverse("bo_tenders:liste"))
    assert reponse.context["nb_ouverts"] == 1 and reponse.context["nb_sans_offre"] == 0
    assert reponse.context["prix_moyen_retenu"] is None
    assert not client.get(reverse("bo_tenders:liste"), {"statut": "ATTRIBUE"}).context["object_list"]
    detail = client.get(reverse("bo_tenders:detail", args=[appel_offre.pk]))
    assert list(detail.context["offres"]) == [offre]


def test_backoffice_appels_interdit_aux_utilisateurs(client, pme, appel_offre):
    client.force_login(pme)
    assert client.get(reverse("bo_tenders:detail", args=[appel_offre.pk])).status_code == 403


# ---------------------------------------------------------------- IA n° 2 : aide au choix d'une offre


def _offre_resumee(offre_id, prix, ecart, note):
    juste = round(prix / (1 + ecart / 100), 2)
    return {
        "offre_id": offre_id,
        "transporteur": f"T{offre_id}",
        "prix": prix,
        "prix_juste": juste,
        "ecart_pct": ecart,
        "note": note,
        "depart": "2026-11-02",
    }


def _recommandation(appel):
    appel.refresh_from_db()
    return appel.recommandation_statut, appel.recommandation_ia


def _mettre_en_cours(appel):
    AppelOffre.objects.filter(pk=appel.pk).update(recommandation_statut=AppelOffre.Recommandation.EN_COURS)


def _rendre_prete(appel, offre):
    AppelOffre.objects.filter(pk=appel.pk).update(
        recommandation_statut=AppelOffre.Recommandation.PRETE,
        recommandation_ia={"offre_id": offre.pk, "explication": "Test.", "methode": "règle"},
        recommandation_duree_ms=3,
    )


@pytest.fixture
def troisieme_transporteur(db):
    user = Utilisateur.objects.create_user("rania@test.tn", "motdepasse123", role=Role.TRANSPORTEUR, first_name="Rania")
    ProfilTransporteur.objects.create(utilisateur=user, statut_validation=ProfilTransporteur.Statut.VALIDE)
    vehicule = Vehicule.objects.create(
        transporteur=user, type=Vehicule.Type.CAMION, immatriculation="555 TU 1111", capacite_kg=2000, capacite_m3=10
    )
    trajet = Trajet.objects.create(
        transporteur=user,
        vehicule=vehicule,
        ville_depart="Monastir",
        ville_arrivee="Tunis",
        date_depart=timezone.now() + timedelta(days=2),
        capacite_dispo_kg=Decimal("1500"),
        capacite_dispo_m3=Decimal("8"),
        distance_km=160,
    )
    return user, trajet


def test_regle_privilegie_le_rapport_prix_fiabilite():
    resume = [_offre_resumee(1, 80, -20, 2.0), _offre_resumee(2, 95, -5, 4.8)]
    resultat = recommander_par_regle(resume)
    assert resultat["offre_id"] == 2 and resultat["methode"] == "règle"
    assert "4,8/5" in resultat["explication"] and "5 % sous le prix juste" in resultat["explication"]


def test_regle_sans_note_ni_prix_juste():
    resume = [_offre_resumee(1, 120, 10, None), _offre_resumee(2, 100, 0, None)]
    resume[0].update(prix_juste=None, ecart_pct=None)
    resultat = recommander_par_regle(resume)
    assert resultat["offre_id"] == 2 and "pas encore de note" in resultat["explication"]


def test_recommandation_sans_offre():
    with pytest.raises(ValueError):
        recommander_depuis_resume([])


def test_tache_en_mode_de_repli(appel_offre, offre, offre_concurrente):
    _mettre_en_cours(appel_offre)
    calculer_recommandation(appel_offre.pk)
    statut, reco = _recommandation(appel_offre)
    assert statut == AppelOffre.Recommandation.PRETE
    assert reco["offre_id"] == offre.pk and reco["methode"] == "règle" and reco["explication"]
    assert appel_offre.recommandation_duree_ms is not None


def test_tache_avec_llm_mocke(settings, appel_offre, offre, offre_concurrente):
    settings.AI_API_KEY, settings.AI_MODEL = "cle-de-test", "modele-test"
    reponse = json.dumps({"offre_id": offre_concurrente.pk, "explication": "Départ plus sûr et bonne réputation."})
    _mettre_en_cours(appel_offre)
    with mock.patch("apps.core.ai.demander", return_value=reponse) as appel_llm:
        calculer_recommandation(appel_offre.pk)
    statut, reco = _recommandation(appel_offre)
    assert statut == AppelOffre.Recommandation.PRETE
    assert reco == {
        "offre_id": offre_concurrente.pk,
        "explication": "Départ plus sûr et bonne réputation.",
        "methode": "LLM (modele-test)",
    }
    assert str(offre.pk) in appel_llm.call_args.args[0]  # le résumé des offres est bien envoyé


@pytest.mark.parametrize(
    "reponse",
    ['{"offre_id": 999999, "explication": "Offre inventée"}', '{"offre_id": "%s"}', "Je ne sais pas."],
)
def test_reponse_llm_invalide_donne_la_regle(settings, appel_offre, offre, offre_concurrente, reponse):
    settings.AI_API_KEY = "cle-de-test"
    _mettre_en_cours(appel_offre)
    with mock.patch("apps.core.ai.demander", return_value=reponse.replace("%s", str(offre.pk))):
        calculer_recommandation(appel_offre.pk)
    statut, reco = _recommandation(appel_offre)
    assert statut == AppelOffre.Recommandation.PRETE
    assert reco["offre_id"] == offre.pk and reco["methode"].startswith("règle")


def test_tache_en_erreur(appel_offre, offre, offre_concurrente):
    _mettre_en_cours(appel_offre)
    with mock.patch("apps.tenders.tasks.recommander_offre", side_effect=RuntimeError("panne")):
        calculer_recommandation(appel_offre.pk)
    assert _recommandation(appel_offre) == (AppelOffre.Recommandation.ERREUR, None)


def test_tache_n_ecrase_pas_un_resultat_perime(appel_offre, offre, offre_concurrente):
    calculer_recommandation(appel_offre.pk)  # analyse annulée entre-temps (statut vide)
    assert _recommandation(appel_offre) == ("", None)
    calculer_recommandation(999_999)  # appel supprimé : aucune erreur


def test_lancer_l_aide_au_choix(client, pme, appel_offre, offre, offre_concurrente):
    client.force_login(pme)
    url = reverse("tenders:recommander", args=[appel_offre.pk])
    assert client.get(url).status_code == 405
    html = client.post(url, follow=True).content.decode()
    assert "Analyse en cours" in html  # message de lancement (Celery s'exécute tout de suite en test)
    assert "Offre recommandée : Karim — 90,00 DT" in html and "Recommandée par l’aide au choix" in html
    assert "Méthode : règle" in html and "vous restez libre" in html


@pytest.mark.parametrize("cas", ["une_offre", "appel_attribue", "deja_en_cours"])
def test_lancer_refuse(client, pme, appel_offre, offre, offre_concurrente, cas):
    if cas == "une_offre":
        offre_concurrente.delete()
    elif cas == "appel_attribue":
        AppelOffre.objects.filter(pk=appel_offre.pk).update(statut=AppelOffre.Statut.ATTRIBUE)
    else:
        _mettre_en_cours(appel_offre)
    client.force_login(pme)
    with mock.patch("apps.tenders.views.calculer_recommandation.delay") as delay:
        client.post(reverse("tenders:recommander", args=[appel_offre.pk]))
    delay.assert_not_called()


def test_lancer_sans_celery(client, pme, appel_offre, offre, offre_concurrente):
    client.force_login(pme)
    with mock.patch("apps.tenders.views.calculer_recommandation.delay", side_effect=ConnectionError("Redis")):
        html = client.post(reverse("tenders:recommander", args=[appel_offre.pk]), follow=True).content.decode()
    assert _recommandation(appel_offre)[0] == AppelOffre.Recommandation.ERREUR
    assert "n’a pas pu démarrer" in html and "L’analyse n’a pas abouti" in html and "Réessayer" in html


def test_aide_au_choix_permissions(client, autre_pme, transporteur, appel_offre, offre, offre_concurrente):
    urls = [
        ("post", reverse("tenders:recommander", args=[appel_offre.pk])),
        ("get", reverse("tenders:recommandation_statut", args=[appel_offre.pk])),
    ]
    for methode, url in urls:
        assert getattr(client, methode)(url).status_code == 302  # anonyme → connexion
    client.force_login(autre_pme)
    for methode, url in urls:
        assert getattr(client, methode)(url).status_code == 404
    client.force_login(transporteur)
    for methode, url in urls:
        assert getattr(client, methode)(url).status_code == 403
    assert _recommandation(appel_offre)[0] == ""


def test_endpoint_json(client, pme, appel_offre, offre, offre_concurrente):
    client.force_login(pme)
    url = reverse("tenders:recommandation_statut", args=[appel_offre.pk])
    _mettre_en_cours(appel_offre)
    assert client.get(url).json() == {"statut": "EN_COURS", "recommandation": None, "duree_ms": None}
    html = client.get(reverse("tenders:detail", args=[appel_offre.pk])).content.decode()
    assert 'aria-live="polite"' in html and "Analyse en cours" in html and "aide_au_choix.js" in html
    calculer_recommandation(appel_offre.pk)
    data = client.get(url).json()
    assert data["statut"] == "PRETE" and data["recommandation"]["offre_id"] == offre.pk and data["duree_ms"] >= 0


def test_nouvelle_offre_efface_la_recommandation(client, appel_offre, offre, offre_concurrente, troisieme_transporteur):
    _rendre_prete(appel_offre, offre)
    rania, trajet = troisieme_transporteur
    client.force_login(rania)
    client.post(reverse("tenders:offre_creer", args=[appel_offre.pk]), {"trajet": trajet.pk, "prix": "85"})
    assert Offre.objects.filter(transporteur=rania).exists()
    assert _recommandation(appel_offre) == ("", None)


def test_modifier_ou_retirer_une_offre_efface_la_recommandation(client, transporteur, appel_offre, offre, trajet):
    client.force_login(transporteur)
    _rendre_prete(appel_offre, offre)
    client.post(reverse("tenders:offre_modifier", args=[offre.pk]), {"trajet": trajet.pk, "prix": "87"})
    assert _recommandation(appel_offre) == ("", None)
    _rendre_prete(appel_offre, offre)
    client.post(reverse("tenders:offre_retirer", args=[offre.pk]))
    assert _recommandation(appel_offre) == ("", None)
