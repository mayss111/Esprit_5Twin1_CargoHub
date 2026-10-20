"""Vues du module Flotte & trajets — Membre 3.

Point de départ : une page liste front-office et une page liste back-office.
Ajoutez ici vos vues de création, détail, modification…
"""

from apps.core.roles import Role
from apps.core.views import ListeBackofficeView, ListeFrontView

from .models import Trajet, Vehicule


class MesTrajetsView(ListeFrontView):
    model = Trajet
    roles = [Role.TRANSPORTEUR]
    titre = "Mes trajets"
    sous_titre = "Les trajets que vous proposez et leur place libre."
    colonnes = [
        ("ville_depart", "Départ"),
        ("ville_arrivee", "Arrivée"),
        ("date_depart", "Date"),
        ("capacite_dispo_kg", "Place libre (kg)"),
        ("statut", "Statut"),
    ]

    def get_queryset(self):
        return Trajet.objects.filter(transporteur=self.request.user).select_related("vehicule")


class MesVehiculesView(ListeFrontView):
    model = Vehicule
    roles = [Role.TRANSPORTEUR]
    titre = "Mes véhicules"
    sous_titre = "Vos camions et leur capacité."
    colonnes = [
        ("immatriculation", "Immatriculation"),
        ("type", "Type"),
        ("capacite_kg", "Capacité (kg)"),
        ("conforme", "Conforme"),
    ]

    def get_queryset(self):
        return Vehicule.objects.filter(transporteur=self.request.user)


class BackofficeVehiculeView(ListeBackofficeView):
    model = Vehicule
    titre = "Véhicules"
    colonnes = [
        ("immatriculation", "Immatriculation"),
        ("transporteur", "Transporteur"),
        ("type", "Type"),
        ("conforme", "Conforme"),
    ]

    def get_queryset(self):
        return Vehicule.objects.select_related("transporteur")
