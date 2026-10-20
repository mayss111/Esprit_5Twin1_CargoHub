"""Vues du module Assurance & sinistres — Membre 2.

Point de départ : une page liste front-office et une page liste back-office.
Ajoutez ici vos vues de création, détail, modification…
"""

from apps.core.roles import Role
from apps.core.views import ListeBackofficeView, ListeFrontView

from .models import PoliceAssurance, Sinistre


class MesAssurancesView(ListeFrontView):
    model = PoliceAssurance
    roles = [Role.PME]
    titre = "Mes assurances"
    sous_titre = "Vos marchandises assurées et vos sinistres."
    colonnes = [("expedition", "Expédition"), ("valeur_declaree", "Valeur"), ("prime", "Prime"), ("statut", "Statut")]

    def get_queryset(self):
        return PoliceAssurance.objects.filter(expedition__pme=self.request.user)


class BackofficeSinistreView(ListeBackofficeView):
    model = Sinistre
    titre = "Sinistres à traiter"
    colonnes = [("pk", "N°"), ("police", "Police"), ("statut", "Statut"), ("created_at", "Déclaré le")]

    def get_queryset(self):
        return Sinistre.objects.select_related("police")
