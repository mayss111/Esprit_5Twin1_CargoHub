"""Vues du module Entretien & conformité — Membre 3.

Point de départ : une page liste front-office et une page liste back-office.
Ajoutez ici vos vues de création, détail, modification…
"""

from apps.core.roles import Role
from apps.core.views import ListeBackofficeView, ListeFrontView

from .models import ControleTechnique, Entretien


class MesEntretiensView(ListeFrontView):
    model = Entretien
    roles = [Role.TRANSPORTEUR]
    titre = "Entretien"
    sous_titre = "Entretiens, visites techniques et dépenses de vos camions."
    colonnes = [
        ("vehicule", "Véhicule"),
        ("type", "Type"),
        ("date", "Date"),
        ("kilometrage", "Km"),
        ("prochaine_echeance", "Prochaine échéance"),
    ]

    def get_queryset(self):
        return Entretien.objects.filter(vehicule__transporteur=self.request.user).select_related("vehicule")


class BackofficeControleTechniqueView(ListeBackofficeView):
    model = ControleTechnique
    titre = "Contrôles techniques"
    colonnes = [
        ("vehicule", "Véhicule"),
        ("date_controle", "Contrôlé le"),
        ("date_expiration", "Expire le"),
        ("favorable", "Favorable"),
    ]

    def get_queryset(self):
        return ControleTechnique.objects.select_related("vehicule")
