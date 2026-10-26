"""Tableau de bord global du back-office — Membre 5."""

from django.db.models import Sum
from django.http import HttpResponse
from django.utils import timezone
from django.views.generic import TemplateView, View

from apps.accounts.models import Utilisateur
from apps.bookings.models import Reservation
from apps.core.mixins import AdminRequiredMixin
from apps.core.roles import Role
from apps.fleet.models import Trajet, Vehicule
from apps.payments.models import Paiement
from apps.shipments.models import Expedition

from .exports import excel_pilotage, pdf_pilotage

MOIS = ["", "janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]


def _six_mois():
    instant = timezone.now()
    annee, mois = instant.year, instant.month
    couples = []
    for _ in range(6):
        couples.append((annee, mois))
        mois -= 1
        if mois == 0:
            mois, annee = 12, annee - 1
    return list(reversed(couples))


def indicateurs():
    nb_vehicules = Vehicule.objects.count()
    nb_conformes = Vehicule.objects.filter(statut=Vehicule.Statut.ACTIF, conforme=True).count()
    taux_conformite = round(100 * nb_conformes / nb_vehicules) if nb_vehicules else 0
    kpis = [
        ("PME inscrites", Utilisateur.objects.filter(role=Role.PME).count(), "building"),
        ("Transporteurs", Utilisateur.objects.filter(role=Role.TRANSPORTEUR).count(), "truck"),
        ("Véhicules", nb_vehicules, "truck-front"),
        ("Taux de conformité (%)", taux_conformite, "shield-check"),
        ("Expéditions", Expedition.objects.count(), "box-seam"),
        ("Trajets ouverts", Trajet.objects.filter(statut=Trajet.Statut.OUVERT).count(), "signpost-split"),
        ("Réservations", Reservation.objects.count(), "calendar-check"),
        (
            "Chiffre d’affaires (DT)",
            float(Paiement.objects.filter(statut=Paiement.Statut.PAYE).aggregate(t=Sum("montant"))["t"] or 0),
            "cash-coin",
        ),
    ]
    series = []
    for annee, mois in _six_mois():
        encaisse = Paiement.objects.filter(
            statut=Paiement.Statut.PAYE, created_at__year=annee, created_at__month=mois
        ).aggregate(t=Sum("montant"))["t"]
        series.append(
            {
                "mois": f"{MOIS[mois]} {annee}",
                "reservations": Reservation.objects.filter(created_at__year=annee, created_at__month=mois).count(),
                "encaissements": float(encaisse or 0),
            }
        )
    ouverts = Trajet.objects.filter(statut=Trajet.Statut.OUVERT).select_related("vehicule")
    taux = []
    for trajet in ouverts:
        capacite = trajet.vehicule.capacite_kg or 0
        if capacite:
            taux.append(float((capacite - trajet.capacite_dispo_kg) / capacite * 100))
    remplissage = round(sum(taux) / len(taux), 1) if taux else 0
    return kpis, series, remplissage


class AccueilBackofficeView(AdminRequiredMixin, TemplateView):
    template_name = "dashboard/accueil.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        kpis, series, remplissage = indicateurs()
        ctx["kpis"] = kpis
        ctx["series"] = series
        ctx["remplissage"] = remplissage
        ctx["dernieres_reservations"] = Reservation.objects.select_related("trajet", "expedition", "expedition__pme")[
            :8
        ]
        return ctx


class ExportExcelView(AdminRequiredMixin, View):
    def get(self, request):
        kpis, series, _remplissage = indicateurs()
        reponse = HttpResponse(
            excel_pilotage(kpis, series),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        reponse["Content-Disposition"] = 'attachment; filename="cargohub-pilotage.xlsx"'
        return reponse


class ExportPdfView(AdminRequiredMixin, View):
    def get(self, request):
        kpis, series, remplissage = indicateurs()
        reponse = HttpResponse(pdf_pilotage(kpis, series, remplissage), content_type="application/pdf")
        reponse["Content-Disposition"] = 'attachment; filename="cargohub-pilotage.pdf"'
        return reponse
