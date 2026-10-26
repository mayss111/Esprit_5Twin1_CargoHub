"""Tableau de bord global du back-office — Membre 5.

Les graphiques (Chart.js) et l'export Excel / PDF sont à ajouter ici.
"""

from django.db.models import Sum
from django.views.generic import TemplateView

from apps.accounts.models import Utilisateur
from apps.accounts.reliability import score_fiabilite
from apps.bookings.models import Reservation
from apps.core.mixins import AdminRequiredMixin
from apps.core.roles import Role
from apps.fleet.models import Trajet
from apps.payments.models import Paiement
from apps.shipments.models import Expedition


class AccueilBackofficeView(AdminRequiredMixin, TemplateView):
    template_name = "dashboard/accueil.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["kpis"] = [
            ("PME inscrites", Utilisateur.objects.filter(role=Role.PME).count(), "building"),
            ("Transporteurs", Utilisateur.objects.filter(role=Role.TRANSPORTEUR).count(), "truck"),
            ("Expéditions", Expedition.objects.count(), "box-seam"),
            ("Trajets ouverts", Trajet.objects.filter(statut=Trajet.Statut.OUVERT).count(), "signpost-split"),
            ("Réservations", Reservation.objects.count(), "calendar-check"),
            (
                "Chiffre d’affaires (DT)",
                Paiement.objects.filter(statut=Paiement.Statut.PAYE).aggregate(t=Sum("montant"))["t"] or 0,
                "cash-coin",
            ),
        ]
        ctx["dernieres_reservations"] = Reservation.objects.select_related("trajet", "expedition")[:8]
        ctx["scores_fiabilite"] = []
        for utilisateur in Utilisateur.objects.filter(role__in=[Role.PME, Role.TRANSPORTEUR]).order_by("role", "email"):
            resultat = score_fiabilite(utilisateur)
            ctx["scores_fiabilite"].append({"utilisateur": utilisateur, "resultat": resultat})
        return ctx
