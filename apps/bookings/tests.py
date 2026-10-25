"""Tests du module Matching & réservations (M4) : services, règles du modèle, pages par rôle, back-office."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.bookings import services
from apps.bookings.forms import FiltreReservationsForm
from apps.bookings.models import HistoriqueStatut, Notification, Reservation
from apps.fleet.models import Trajet
from apps.shipments.models import Expedition

S = Reservation.Statut


@pytest.fixture
def reservation(expedition, trajet):
    return services.reserver(expedition, trajet)


def _statut(reservation):
    reservation.refresh_from_db()
    return reservation.statut


# ---------------------------------------------------------------- services (tests unitaires)


def test_trajet_compatible_trouve(expedition, trajet):
    resultats = services.trajets_compatibles(expedition)
    assert resultats and resultats[0][0] == trajet
    assert resultats[0][1] >= 90


def test_trajet_hors_itineraire_exclu(expedition, autre_trajet):
    assert autre_trajet not in [t for t, _ in services.trajets_compatibles(expedition)]


def test_reserver_cree_une_notification(expedition, trajet):
    reservation = services.reserver(expedition, trajet)
    assert reservation.statut == S.EN_ATTENTE
    assert reservation.prix_convenu == Decimal("85") and reservation.score_matching >= 90
    assert Notification.objects.filter(destinataire=trajet.transporteur).exists()


def test_accepter_retire_la_place(expedition, trajet, transporteur):
    reservation = services.reserver(expedition, trajet)
    services.changer_statut(reservation, S.ACCEPTEE, par=transporteur)
    trajet.refresh_from_db()
    assert trajet.capacite_dispo_kg == Decimal("1000") - Decimal("300")  # 12 cartons x 25 kg


def test_annuler_rend_la_place(expedition, trajet):
    reservation = services.reserver(expedition, trajet)
    services.changer_statut(reservation, S.ACCEPTEE)
    services.changer_statut(reservation, S.ANNULEE)
    trajet.refresh_from_db()
    assert trajet.capacite_dispo_kg == Decimal("1000")


def test_pas_de_sur_reservation(expedition, trajet):
    trajet.capacite_dispo_kg = Decimal("100")
    trajet.save()
    reservation = services.reserver(expedition, trajet)
    with pytest.raises(services.ReservationImpossible):
        services.changer_statut(reservation, S.ACCEPTEE)


def test_transition_interdite(expedition, trajet):
    reservation = services.reserver(expedition, trajet)
    with pytest.raises(services.ReservationImpossible):
        services.changer_statut(reservation, S.LIVREE)


def test_historique_et_motif(reservation, admin_user):
    services.changer_statut(reservation, S.ANNULEE, par=admin_user, motif="Litige : colis non conforme")
    h = HistoriqueStatut.objects.get(reservation=reservation)
    assert (h.ancien, h.nouveau, h.par, h.motif) == (S.EN_ATTENTE, S.ANNULEE, admin_user, "Litige : colis non conforme")
    assert str(h) == "EN_ATTENTE → ANNULEE"


@pytest.mark.parametrize(
    "depart, arrivee, autorise",
    [
        (S.EN_ATTENTE, S.ACCEPTEE, True),
        (S.EN_ATTENTE, S.REFUSEE, True),
        (S.ACCEPTEE, S.EN_TRANSIT, True),
        (S.EN_TRANSIT, S.LIVREE, True),
        (S.EN_ATTENTE, S.LIVREE, False),
        (S.REFUSEE, S.ACCEPTEE, False),
        (S.LIVREE, S.ANNULEE, False),
        (S.EN_TRANSIT, S.ANNULEE, False),
    ],
)
def test_transitions_du_modele(depart, arrivee, autorise):
    assert Reservation(statut=depart).peut_passer_a(arrivee) is autorise


def test_annulable():
    assert Reservation(statut=S.ACCEPTEE).annulable
    assert not Reservation(statut=S.EN_TRANSIT).annulable


def test_filtre_dates_incoherentes(db):
    form = FiltreReservationsForm({"du": "2026-10-20", "au": "2026-10-01"})
    assert not form.is_valid() and "au" in form.errors


# ---------------------------------------------------------------- PME : trouver un camion et réserver


def test_trouver_un_camion(client, pme, expedition):
    client.force_login(pme)
    reponse = client.get(reverse("bookings:trouver"))
    assert reponse.status_code == 200
    assert list(reponse.context["expeditions"]) == [expedition]


@pytest.mark.parametrize("nom", ["bookings:trouver", "bookings:demandes"])
def test_pages_interdites_au_mauvais_role(client, pme, transporteur, nom):
    mauvais = transporteur if nom == "bookings:trouver" else pme
    client.force_login(mauvais)
    assert client.get(reverse(nom)).status_code == 403


@pytest.mark.parametrize("nom", ["bookings:trouver", "bookings:demandes", "bookings:liste"])
def test_anonyme_redirige_vers_connexion(client, nom):
    reponse = client.get(reverse(nom))
    assert reponse.status_code == 302 and reverse("accounts:connexion") in reponse.url


def test_camions_compatibles(client, pme, expedition, trajet):
    client.force_login(pme)
    reponse = client.get(reverse("bookings:camions", args=[expedition.pk]))
    html = reponse.content.decode()
    assert reponse.status_code == 200
    assert reponse.context["resultats"][0][0] == trajet
    assert 'role="progressbar"' in html and 'aria-valuenow="100"' in html and "Score 100 / 100" in html


def test_camions_expedition_d_une_autre_pme(client, autre_pme, expedition):
    client.force_login(autre_pme)
    assert client.get(reverse("bookings:camions", args=[expedition.pk])).status_code == 404


def test_camions_expedition_non_publiee(client, pme, expedition, trajet):
    Expedition.objects.filter(pk=expedition.pk).update(statut=Expedition.Statut.BROUILLON)
    client.force_login(pme)
    reponse = client.get(reverse("bookings:camions", args=[expedition.pk]))
    assert reponse.context["resultats"] == [] and "n’est pas publiée" in reponse.content.decode()


def test_reserver(client, pme, expedition, trajet):
    client.force_login(pme)
    url = reverse("bookings:reserver", args=[expedition.pk, trajet.pk])
    assert client.get(url).status_code == 405  # jamais en GET
    reponse = client.post(url)
    reservation = Reservation.objects.get()
    assert reponse.url == reverse("bookings:detail", args=[reservation.pk])
    assert reservation.statut == S.EN_ATTENTE

    reponse = client.post(url, follow=True)  # deuxième demande sur le même trajet
    assert Reservation.objects.count() == 1 and "déjà demandé" in reponse.content.decode()


def test_reserver_expedition_non_publiee(client, pme, expedition, trajet):
    Expedition.objects.filter(pk=expedition.pk).update(statut=Expedition.Statut.BROUILLON)
    client.force_login(pme)
    client.post(reverse("bookings:reserver", args=[expedition.pk, trajet.pk]))
    assert not Reservation.objects.exists()


def test_reserver_trajet_ferme_ou_expedition_d_autrui(client, pme, autre_pme, expedition, trajet):
    Trajet.objects.filter(pk=trajet.pk).update(statut=Trajet.Statut.COMPLET)
    client.force_login(pme)
    assert client.post(reverse("bookings:reserver", args=[expedition.pk, trajet.pk])).status_code == 404
    Trajet.objects.filter(pk=trajet.pk).update(statut=Trajet.Statut.OUVERT)
    client.force_login(autre_pme)
    assert client.post(reverse("bookings:reserver", args=[expedition.pk, trajet.pk])).status_code == 404


# ---------------------------------------------------------------- mes réservations


def test_liste_et_filtre(client, pme, transporteur, reservation):
    for user in (pme, transporteur):
        client.force_login(user)
        assert list(client.get(reverse("bookings:liste")).context["object_list"]) == [reservation]
    assert not client.get(reverse("bookings:liste"), {"statut": "ACCEPTEE"}).context["object_list"]
    assert client.get(reverse("bookings:liste"), {"statut": "n-importe-quoi"}).context["statut_actif"] == ""


def test_liste_ne_montre_pas_les_reservations_des_autres(client, autre_pme, autre_transporteur, reservation):
    for user in (autre_pme, autre_transporteur):
        client.force_login(user)
        assert not client.get(reverse("bookings:liste")).context["object_list"]


def test_detail(client, pme, transporteur, reservation, autre_pme):
    client.force_login(pme)
    reponse = client.get(reverse("bookings:detail", args=[reservation.pk]))
    assert reponse.status_code == 200 and reponse.context["est_pme"]
    assert "Annuler la réservation" in reponse.content.decode()
    client.force_login(transporteur)
    reponse = client.get(reverse("bookings:detail", args=[reservation.pk]))
    assert reponse.context["est_transporteur"] and 'value="accepter"' in reponse.content.decode()
    client.force_login(autre_pme)
    assert client.get(reverse("bookings:detail", args=[reservation.pk])).status_code == 404


def test_annuler_une_reservation_acceptee(client, pme, reservation, trajet):
    services.changer_statut(reservation, S.ACCEPTEE)
    client.force_login(pme)
    url = reverse("bookings:annuler", args=[reservation.pk])
    assert "Oui, annuler" in client.get(url).content.decode()
    client.post(url)
    assert _statut(reservation) == S.ANNULEE
    trajet.refresh_from_db()
    assert trajet.capacite_dispo_kg == Decimal("1000")  # place rendue


def test_annuler_impossible(client, pme, reservation):
    services.changer_statut(reservation, S.REFUSEE)
    client.force_login(pme)
    url = reverse("bookings:annuler", args=[reservation.pk])
    assert "ne peut plus être annulée" in client.get(url).content.decode()
    reponse = client.post(url, follow=True)
    assert "ne peut plus être annulée" in reponse.content.decode() and _statut(reservation) == S.REFUSEE


def test_annuler_reserve_a_la_pme_proprietaire(client, transporteur, autre_pme, reservation):
    client.force_login(transporteur)
    assert client.post(reverse("bookings:annuler", args=[reservation.pk])).status_code == 403
    client.force_login(autre_pme)
    assert client.post(reverse("bookings:annuler", args=[reservation.pk])).status_code == 404
    assert _statut(reservation) == S.EN_ATTENTE


# ---------------------------------------------------------------- transporteur : demandes reçues


def test_demandes_recues(client, transporteur, autre_transporteur, reservation):
    client.force_login(transporteur)
    assert list(client.get(reverse("bookings:demandes")).context["object_list"]) == [reservation]
    client.force_login(autre_transporteur)
    assert not client.get(reverse("bookings:demandes")).context["object_list"]


def test_accepter_une_demande(client, transporteur, reservation, trajet):
    client.force_login(transporteur)
    reponse = client.post(reverse("bookings:repondre", args=[reservation.pk]), {"action": "accepter"})
    assert reponse.url == reverse("bookings:demandes")
    assert _statut(reservation) == S.ACCEPTEE
    trajet.refresh_from_db()
    assert trajet.capacite_dispo_kg == Decimal("700")


def test_refuser_une_demande_depuis_le_detail(client, transporteur, reservation):
    client.force_login(transporteur)
    reponse = client.post(
        reverse("bookings:repondre", args=[reservation.pk]), {"action": "refuser", "retour": "detail"}
    )
    assert reponse.url == reverse("bookings:detail", args=[reservation.pk])
    assert _statut(reservation) == S.REFUSEE


def test_repondre_cas_d_erreur(client, transporteur, reservation, trajet):
    client.force_login(transporteur)
    url = reverse("bookings:repondre", args=[reservation.pk])
    assert "Action inconnue" in client.post(url, {"action": "livrer"}, follow=True).content.decode()
    Trajet.objects.filter(pk=trajet.pk).update(capacite_dispo_kg=Decimal("10"))
    assert "Plus assez de place" in client.post(url, {"action": "accepter"}, follow=True).content.decode()
    assert _statut(reservation) == S.EN_ATTENTE


def test_repondre_reserve_au_transporteur_du_trajet(client, pme, autre_transporteur, reservation):
    client.force_login(autre_transporteur)
    assert client.post(reverse("bookings:repondre", args=[reservation.pk]), {"action": "accepter"}).status_code == 404
    client.force_login(pme)
    assert client.post(reverse("bookings:repondre", args=[reservation.pk]), {"action": "accepter"}).status_code == 403
    assert _statut(reservation) == S.EN_ATTENTE


# ---------------------------------------------------------------- back-office


def test_backoffice_filtres(client, admin_user, reservation, pme, transporteur, autre_pme):
    client.force_login(admin_user)
    url = reverse("bo_bookings:liste")

    def resultats(**filtres):
        return list(client.get(url, filtres).context["object_list"])

    aujourd_hui = timezone.localdate()
    assert resultats() == [reservation]
    assert resultats(statut="EN_ATTENTE") == [reservation] and resultats(statut="LIVREE") == []
    assert resultats(pme=pme.pk) == [reservation] and resultats(pme=autre_pme.pk) == []
    assert resultats(transporteur=transporteur.pk) == [reservation]
    assert resultats(du=aujourd_hui.isoformat(), au=aujourd_hui.isoformat()) == [reservation]
    assert resultats(du=(aujourd_hui + timedelta(days=1)).isoformat()) == []
    assert resultats(q=f"#{reservation.pk}") == [reservation]
    assert resultats(q="karim@test") == [reservation] and resultats(q="introuvable") == []
    assert resultats(du="2026-10-20", au="2026-10-01") == [reservation]  # filtre invalide : ignoré


def test_backoffice_annuler_pour_litige(client, admin_user, reservation):
    client.force_login(admin_user)
    assert client.get(reverse("bo_bookings:detail", args=[reservation.pk])).status_code == 200
    url = reverse("bo_bookings:litige", args=[reservation.pk])
    assert client.get(url).status_code == 405

    reponse = client.post(url, {"motif": "court"})  # motif trop court
    assert reponse.status_code == 200 and reponse.context["form_litige"].errors
    assert _statut(reservation) == S.EN_ATTENTE

    client.post(url, {"motif": "La PME conteste le prix convenu"})
    assert _statut(reservation) == S.ANNULEE
    assert reservation.historique.get().motif == "Litige : La PME conteste le prix convenu"


def test_backoffice_litige_impossible(client, admin_user, reservation):
    Reservation.objects.filter(pk=reservation.pk).update(statut=S.LIVREE)
    client.force_login(admin_user)
    reponse = client.post(
        reverse("bo_bookings:litige", args=[reservation.pk]), {"motif": "Colis abîmé à la livraison"}, follow=True
    )
    assert "ne peut plus être annulée" in reponse.content.decode() and _statut(reservation) == S.LIVREE


@pytest.mark.parametrize("nom", ["detail", "litige"])
def test_backoffice_interdit_aux_utilisateurs(client, pme, reservation, nom):
    client.force_login(pme)
    assert client.post(reverse(f"bo_bookings:{nom}", args=[reservation.pk])).status_code == 403
