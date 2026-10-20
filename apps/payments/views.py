"""Vues du module Paiement & facturation — Membre 5.

Point de départ : une page liste front-office et une page liste back-office.
Ajoutez ici vos vues de création, détail, modification…
"""

from django.db.models import Q

from apps.core.views import ListeBackofficeView, ListeFrontView

from .models import Paiement


class MesPaiementsView(ListeFrontView):
    model = Paiement
    roles = []
    titre = "Paiements"
    sous_titre = "Vos paiements, factures et revenus."
    colonnes = [("pk", "N°"), ("reservation", "Réservation"), ("montant", "Montant (DT)"), ("statut", "Statut")]

    def get_queryset(self):
        return Paiement.objects.filter(
            Q(reservation__expedition__pme=self.request.user) | Q(reservation__trajet__transporteur=self.request.user)
        )


class BackofficePaiementView(ListeBackofficeView):
    model = Paiement
    titre = "Paiements"
    colonnes = [("pk", "N°"), ("reservation", "Réservation"), ("montant", "Montant (DT)"), ("statut", "Statut")]

    def get_queryset(self):
        return Paiement.objects.select_related("reservation")
