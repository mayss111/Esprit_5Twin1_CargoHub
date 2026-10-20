"""Vues du module Contrats & documents — Membre 1.

Point de départ : une page liste front-office et une page liste back-office.
Ajoutez ici vos vues de création, détail, modification…
"""

from django.db.models import Q

from apps.core.views import ListeBackofficeView, ListeFrontView

from .models import Contrat


class MesContratsView(ListeFrontView):
    model = Contrat
    roles = []
    titre = "Mes contrats"
    sous_titre = "Contrats et lettres de voiture de vos transports."
    colonnes = [("reservation", "Réservation"), ("est_signe", "Signé"), ("created_at", "Créé le")]

    def get_queryset(self):
        return Contrat.objects.filter(
            Q(reservation__expedition__pme=self.request.user) | Q(reservation__trajet__transporteur=self.request.user)
        )


class BackofficeContratView(ListeBackofficeView):
    model = Contrat
    titre = "Contrats"
    colonnes = [("reservation", "Réservation"), ("est_signe", "Signé"), ("created_at", "Créé le")]

    def get_queryset(self):
        return Contrat.objects.all()
