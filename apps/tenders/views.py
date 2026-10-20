"""Vues du module Appels d’offres & négociation — Membre 4.

Point de départ : une page liste front-office et une page liste back-office.
Ajoutez ici vos vues de création, détail, modification…
"""

from apps.core.roles import Role
from apps.core.views import ListeBackofficeView, ListeFrontView

from .models import AppelOffre


class AppelsOffresView(ListeFrontView):
    model = AppelOffre
    roles = []
    titre = "Appels d’offres"
    sous_titre = "PME : vos appels d’offres. Transporteur : les appels ouverts."
    colonnes = [("pk", "N°"), ("expedition", "Expédition"), ("date_cloture", "Clôture"), ("statut", "Statut")]

    def get_queryset(self):
        return (
            AppelOffre.objects.filter(expedition__pme=self.request.user)
            if self.request.user.role == Role.PME
            else AppelOffre.objects.filter(statut=AppelOffre.Statut.OUVERT)
        )


class BackofficeAppelOffreView(ListeBackofficeView):
    model = AppelOffre
    titre = "Appels d’offres"
    colonnes = [("pk", "N°"), ("expedition", "Expédition"), ("date_cloture", "Clôture"), ("statut", "Statut")]

    def get_queryset(self):
        return AppelOffre.objects.all()
