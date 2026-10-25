"""Tests du module Appels d’offres & négociation (M4) : règles, retenir une offre, IA, pages par rôle, back-office."""

from datetime import timedelta
from decimal import Decimal
from io import StringIO
from unittest import mock

import pytest
from django.core.management import call_command
from django.db import IntegrityError
from django.urls import reverse
from django.utils import timezone

from apps.bookings.models import Notification, Reservation
from apps.bookings.services import ReservationImpossible
from apps.fleet.models import Trajet
from apps.tenders.ai import suggerer_prix
from apps.tenders.forms import AppelOffreForm, OffreForm
from apps.tenders.models import AppelOffre, Offre
from apps.tenders.services import retenir_offre
from apps.tenders.tasks import cloturer_appels_offres


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
    assert client.get(url, {"expedition": expedition.pk}).context["form"].initial["expedition"] == str(expedition.pk)
    reponse = client.post(url, {"expedition": expedition.pk, "date_cloture": _dans(-1), "prix_max": "150"})
    assert reponse.status_code == 200 and not AppelOffre.objects.exists()
    reponse = client.post(url, {"expedition": expedition.pk, "date_cloture": _dans(1), "prix_max": "150"})
    appel = AppelOffre.objects.get()
    assert reponse.url == reverse("tenders:detail", args=[appel.pk]) and appel.prix_max == Decimal("150")


def test_creer_sans_expedition_disponible(client, autre_pme):
    client.force_login(autre_pme)
    assert "Publiez d’abord une expédition" in client.get(reverse("tenders:creer")).content.decode()


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
