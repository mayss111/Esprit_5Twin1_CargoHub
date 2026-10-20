"""Vues du module Expéditions — Membre 2.

Point de départ : une page liste front-office et une page liste back-office.
Ajoutez ici vos vues de création, détail, modification…
"""

from apps.core.roles import Role
from apps.core.views import ListeBackofficeView, ListeFrontView

from .models import Expedition


class MesExpeditionsView(ListeFrontView):
    model = Expedition
    roles = [Role.PME]
    titre = "Mes expéditions"
    sous_titre = "Vos demandes d’envoi et leur statut."
    colonnes = [
        ("pk", "N°"),
        ("adresse_depart__ville", "Départ"),
        ("adresse_arrivee__ville", "Arrivée"),
        ("date_souhaitee", "Date"),
        ("statut", "Statut"),
        ("prix_estime", "Prix estimé"),
    ]

    def get_queryset(self):
        return Expedition.objects.filter(pme=self.request.user).select_related("adresse_depart", "adresse_arrivee")


class BackofficeExpeditionView(ListeBackofficeView):
    model = Expedition
    titre = "Toutes les expéditions"
    colonnes = [
        ("pk", "N°"),
        ("pme", "PME"),
        ("adresse_depart__ville", "Départ"),
        ("adresse_arrivee__ville", "Arrivée"),
        ("statut", "Statut"),
    ]

    def get_queryset(self):
        return Expedition.objects.select_related("pme", "adresse_depart", "adresse_arrivee")
