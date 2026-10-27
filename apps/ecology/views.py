"""Rapports d'émissions et d'économies de CO₂ pour les utilisateurs."""

from django.db.models import Q

from apps.core.views import ListeBackofficeView, ListeFrontView

from .models import EmpreinteCarbone


class MonBilanView(ListeFrontView):
    model = EmpreinteCarbone
    roles = []
    titre = "CO₂ économisé grâce au partage"
    sous_titre = "Comparez les émissions de vos expéditions partagées avec un transport dédié."
    template_name = "ecology/bilan.html"
    colonnes = [
        ("reservation", "Réservation"),
        ("distance_km", "Distance (km)"),
        ("co2_economise_kg", "CO₂ économisé (kg)"),
    ]

    def get_queryset(self):
        return EmpreinteCarbone.objects.filter(
            Q(reservation__expedition__pme=self.request.user) | Q(reservation__trajet__transporteur=self.request.user)
        ).select_related("reservation__expedition", "reservation__trajet__vehicule")

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        empreintes = list(self.get_queryset())
        contexte["empreintes"] = empreintes
        contexte["co2_total_economise"] = round(sum(item.co2_economise_kg for item in empreintes), 2)
        contexte["est_transporteur"] = getattr(self.request.user, "role", None) == "TRANSPORTEUR"
        return contexte


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
