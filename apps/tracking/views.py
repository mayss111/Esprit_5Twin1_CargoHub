"""Vues du module Suivi & livraison — Membre 5.

Point de départ : une page liste front-office et une page liste back-office.
Ajoutez ici vos vues de création, détail, modification…
"""

from django.db.models import Q

from apps.bookings.models import Reservation
from apps.core.views import ListeBackofficeView, ListeFrontView

from .models import Incident


class SuiviView(ListeFrontView):
    model = Reservation
    roles = []
    titre = "Suivi des livraisons"
    sous_titre = "Vos transports en cours."
    colonnes = [("pk", "N°"), ("trajet", "Trajet"), ("statut", "Statut")]

    def get_queryset(self):
        return Reservation.objects.filter(
            Q(expedition__pme=self.request.user) | Q(trajet__transporteur=self.request.user),
            statut__in=["ACCEPTEE", "EN_TRANSIT"],
        )


class BackofficeIncidentView(ListeBackofficeView):
    model = Incident
    titre = "Incidents"
    colonnes = [("pk", "N°"), ("type", "Type"), ("declare_par", "Déclaré par"), ("statut", "Statut")]

    def get_queryset(self):
        return Incident.objects.select_related("reservation", "declare_par")
