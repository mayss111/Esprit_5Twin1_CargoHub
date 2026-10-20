"""Vues du module Matching & réservations — Membre 4.

Point de départ : une page liste front-office et une page liste back-office.
Ajoutez ici vos vues de création, détail, modification…
"""

from django.db.models import Q

from apps.core.views import ListeBackofficeView, ListeFrontView

from .models import Reservation


class MesReservationsView(ListeFrontView):
    model = Reservation
    roles = []
    titre = "Réservations"
    sous_titre = "Vos réservations de place dans les camions."
    colonnes = [
        ("pk", "N°"),
        ("trajet", "Trajet"),
        ("statut", "Statut"),
        ("prix_convenu", "Prix"),
        ("score_matching", "Score"),
    ]

    def get_queryset(self):
        return Reservation.objects.filter(
            Q(expedition__pme=self.request.user) | Q(trajet__transporteur=self.request.user)
        ).select_related("trajet")


class BackofficeReservationView(ListeBackofficeView):
    model = Reservation
    titre = "Toutes les réservations"
    colonnes = [("pk", "N°"), ("expedition", "Expédition"), ("trajet", "Trajet"), ("statut", "Statut")]

    def get_queryset(self):
        return Reservation.objects.select_related("trajet", "expedition")
