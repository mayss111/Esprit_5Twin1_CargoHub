"""Vues du module Entrepôts & points relais — Membre 2.

Point de départ : une page liste front-office et une page liste back-office.
Ajoutez ici vos vues de création, détail, modification…
"""

from apps.core.roles import Role
from apps.core.views import ListeBackofficeView, ListeFrontView

from .models import Entrepot


class PointsRelaisView(ListeFrontView):
    model = Entrepot
    roles = [Role.PME]
    titre = "Points relais"
    sous_titre = "Déposez vos colis près de chez vous."
    colonnes = [("nom", "Nom"), ("ville", "Ville"), ("adresse", "Adresse")]

    def get_queryset(self):
        return Entrepot.objects.filter(actif=True)


class BackofficeEntrepotView(ListeBackofficeView):
    model = Entrepot
    titre = "Entrepôts"
    colonnes = [("nom", "Nom"), ("ville", "Ville"), ("capacite_colis", "Capacité"), ("actif", "Actif")]

    def get_queryset(self):
        return Entrepot.objects.all()
