from decimal import Decimal

import pytest

from apps.bookings import services
from apps.bookings.models import Notification, Reservation


def test_trajet_compatible_trouve(expedition, trajet):
    resultats = services.trajets_compatibles(expedition)
    assert resultats and resultats[0][0] == trajet
    assert resultats[0][1] >= 90


def test_reserver_cree_une_notification(expedition, trajet):
    reservation = services.reserver(expedition, trajet)
    assert reservation.statut == Reservation.Statut.EN_ATTENTE
    assert Notification.objects.filter(destinataire=trajet.transporteur).exists()


def test_accepter_retire_la_place(expedition, trajet, transporteur):
    reservation = services.reserver(expedition, trajet)
    services.changer_statut(reservation, Reservation.Statut.ACCEPTEE, par=transporteur)
    trajet.refresh_from_db()
    assert trajet.capacite_dispo_kg == Decimal("1000") - Decimal("300")  # 12 cartons x 25 kg


def test_annuler_rend_la_place(expedition, trajet):
    reservation = services.reserver(expedition, trajet)
    services.changer_statut(reservation, Reservation.Statut.ACCEPTEE)
    services.changer_statut(reservation, Reservation.Statut.ANNULEE)
    trajet.refresh_from_db()
    assert trajet.capacite_dispo_kg == Decimal("1000")


def test_pas_de_sur_reservation(expedition, trajet):
    trajet.capacite_dispo_kg = Decimal("100")
    trajet.save()
    reservation = services.reserver(expedition, trajet)
    with pytest.raises(services.ReservationImpossible):
        services.changer_statut(reservation, Reservation.Statut.ACCEPTEE)


def test_transition_interdite(expedition, trajet):
    reservation = services.reserver(expedition, trajet)
    with pytest.raises(services.ReservationImpossible):
        services.changer_statut(reservation, Reservation.Statut.LIVREE)
