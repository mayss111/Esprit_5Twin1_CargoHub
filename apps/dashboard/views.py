"""Tableau de bord global du back-office — Membre 5.

Les graphiques (Chart.js) et l'export Excel / PDF sont à ajouter ici.
"""

from django.db.models import Sum
from django.views.generic import TemplateView

from apps.accounts.models import Utilisateur
from apps.bookings.models import Reservation
from apps.core.mixins import AdminRequiredMixin
from apps.core.roles import Role
from apps.fleet.models import Trajet, Vehicule
from apps.payments.models import Paiement
from apps.shipments.models import Expedition


class AccueilBackofficeView(AdminRequiredMixin, TemplateView):
    template_name = "dashboard/accueil.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        nb_vehicules = Vehicule.objects.count()
        nb_conformes = Vehicule.objects.filter(statut=Vehicule.Statut.ACTIF, conforme=True).count()
        taux_conformite = round(100 * nb_conformes / nb_vehicules) if nb_vehicules else 0
        ctx["kpis"] = [
            ("PME inscrites", Utilisateur.objects.filter(role=Role.PME).count(), "building"),
            ("Transporteurs", Utilisateur.objects.filter(role=Role.TRANSPORTEUR).count(), "truck"),
            ("Véhicules", nb_vehicules, "truck-front"),
            ("Taux de conformité (%)", taux_conformite, "shield-check"),
            ("Expéditions", Expedition.objects.count(), "box-seam"),
            ("Trajets publiés", Trajet.objects.filter(statut=Trajet.Statut.PUBLIE).count(), "signpost-split"),
            ("Réservations", Reservation.objects.count(), "calendar-check"),
            (
                "Chiffre d’affaires (DT)",
                Paiement.objects.filter(statut=Paiement.Statut.PAYE).aggregate(t=Sum("montant"))["t"] or 0,
                "cash-coin",
            ),
        ]
        ctx["dernieres_reservations"] = Reservation.objects.select_related("trajet", "expedition")[:8]
        return ctx
