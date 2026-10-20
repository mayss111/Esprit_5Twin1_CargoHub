"""Vues du module Impact écologique — Membre 3.

Point de départ : une page liste front-office et une page liste back-office.
Ajoutez ici vos vues de création, détail, modification…
"""

from django.db.models import Q

from apps.core.views import ListeBackofficeView, ListeFrontView

from .models import EmpreinteCarbone


class MonBilanView(ListeFrontView):
    model = EmpreinteCarbone
    roles = []
    titre = "Mon bilan CO₂"
    sous_titre = "Le CO₂ économisé grâce au partage des camions."
    colonnes = [
        ("reservation", "Réservation"),
        ("distance_km", "Distance (km)"),
        ("co2_economise_kg", "CO₂ économisé (kg)"),
    ]

    def get_queryset(self):
        return EmpreinteCarbone.objects.filter(
            Q(reservation__expedition__pme=self.request.user) | Q(reservation__trajet__transporteur=self.request.user)
        )


class BackofficeEmpreinteCarboneView(ListeBackofficeView):
    model = EmpreinteCarbone
    titre = "Empreinte carbone"
    colonnes = [
        ("reservation", "Réservation"),
        ("distance_km", "Distance (km)"),
        ("co2_economise_kg", "CO₂ économisé (kg)"),
    ]

    def get_queryset(self):
        return EmpreinteCarbone.objects.all()
