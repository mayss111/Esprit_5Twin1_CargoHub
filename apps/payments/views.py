"""Vues du module Paiement & facturation — Membre 5."""

from django.conf import settings
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.generic import TemplateView, View

from apps.bookings.models import Reservation
from apps.core.mixins import AdminRequiredMixin, RoleRequiredMixin
from apps.core.roles import Role, est_admin
from apps.core.views import ListeBackofficeView, ListeFrontView

from .forms import CodePromoSaisiForm
from .models import Paiement
from .services import (
    PaiementImpossible,
    appliquer_code,
    assurer_paiement,
    confirmer_session,
    encaisser,
    lancer_checkout,
    paiements_de,
    rembourser,
    verser_commission,
)


def _est_pme(user, paiement) -> bool:
    return paiement.reservation.expedition.pme_id == user.pk


class MesPaiementsView(ListeFrontView):
    model = Paiement
    roles = []
    template_name = "payments/liste.html"
    titre = "Paiements"
    sous_titre = "Factures, codes promo et revenus."

    def get_queryset(self):
        return paiements_de(self.request.user)


class OuvrirPaiementView(RoleRequiredMixin, View):
    roles = [Role.PME]

    def get(self, request, pk):
        return redirect("tracking:detail", pk=pk)

    def post(self, request, pk):
        reservation = get_object_or_404(Reservation.objects.filter(expedition__pme=request.user), pk=pk)
        try:
            paiement = assurer_paiement(reservation)
        except PaiementImpossible as exc:
            messages.error(request, str(exc))
            return redirect("tracking:detail", pk=pk)
        return redirect("payments:detail", pk=paiement.pk)


class PaiementDetailView(RoleRequiredMixin, TemplateView):
    roles = []
    template_name = "payments/detail.html"

    def get_queryset(self):
        return paiements_de(self.request.user)

    def get(self, request, pk):
        self.object = get_object_or_404(self.get_queryset(), pk=pk)
        return self.render_to_response(self._contexte())

    def post(self, request, pk):
        self.object = get_object_or_404(self.get_queryset(), pk=pk)
        if not _est_pme(request.user, self.object) and not est_admin(request.user):
            raise PermissionDenied
        action = request.POST.get("action")
        if action == "code":
            return self._code(request)
        if action == "payer":
            return self._payer(request)
        if action == "carte":
            return self._carte(request)
        messages.error(request, "Action inconnue.")
        return redirect("payments:detail", pk=pk)

    def _contexte(self, form_code=None):
        paiement = self.object
        return {
            "paiement": paiement,
            "est_pme": _est_pme(self.request.user, paiement),
            "form_code": form_code or CodePromoSaisiForm(initial={"code": paiement.code_promo}),
            "stripe": bool(settings.STRIPE_SECRET_KEY),
            "commission": getattr(paiement, "commission", None),
            "facture": getattr(paiement, "facture", None),
        }

    def _code(self, request):
        form = CodePromoSaisiForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Indiquez un code promo.")
            return self.render_to_response(self._contexte(form))
        try:
            appliquer_code(self.object, form.cleaned_data["code"])
        except PaiementImpossible as exc:
            messages.error(request, str(exc))
            return self.render_to_response(self._contexte(form))
        messages.success(request, "Code promo appliqué.")
        return redirect("payments:detail", pk=self.object.pk)

    def _payer(self, request):
        try:
            encaisser(self.object)
        except PaiementImpossible as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, "Paiement enregistré. La facture est disponible.")
        return redirect("payments:detail", pk=self.object.pk)

    def _carte(self, request):
        try:
            url = lancer_checkout(
                self.object,
                request.build_absolute_uri(reverse("payments:stripe_retour")) + "?session_id={CHECKOUT_SESSION_ID}",
                request.build_absolute_uri(reverse("payments:detail", args=[self.object.pk])),
            )
        except PaiementImpossible as exc:
            messages.error(request, str(exc))
            return redirect("payments:detail", pk=self.object.pk)
        return redirect(url)


class FactureView(RoleRequiredMixin, View):
    roles = []

    def get(self, request, pk):
        paiement = get_object_or_404(paiements_de(request.user), pk=pk)
        facture = getattr(paiement, "facture", None)
        if facture is None or not facture.fichier:
            raise Http404("Facture introuvable.")
        return FileResponse(facture.fichier.open("rb"), as_attachment=True, filename=f"{facture.numero}.pdf")


class RetourStripeView(View):
    def get(self, request):
        if not request.user.is_authenticated:
            return redirect("accounts:connexion")
        session_id = request.GET.get("session_id", "")
        try:
            paiement = confirmer_session(session_id)
        except PaiementImpossible as exc:
            messages.error(request, str(exc))
            return redirect("payments:liste")
        if paiement.reservation.expedition.pme_id != request.user.pk and not est_admin(request.user):
            raise PermissionDenied
        messages.success(request, "Paiement par carte confirmé.")
        return redirect("payments:detail", pk=paiement.pk)


class BackofficePaiementView(ListeBackofficeView):
    model = Paiement
    template_name = "payments/backoffice/liste.html"
    titre = "Paiements et commissions"

    def get_queryset(self):
        return Paiement.objects.select_related("reservation", "commission")


class BackofficePaiementDetailView(AdminRequiredMixin, TemplateView):
    template_name = "payments/backoffice/detail.html"

    def get_queryset(self):
        return Paiement.objects.select_related("reservation__expedition__pme", "reservation__trajet__transporteur")

    def get(self, request, pk):
        self.object = get_object_or_404(self.get_queryset(), pk=pk)
        return self.render_to_response(self._contexte())

    def post(self, request, pk):
        paiement = get_object_or_404(self.get_queryset(), pk=pk)
        action = request.POST.get("action")
        try:
            if action == "verser":
                verser_commission(paiement)
                messages.success(request, "Commission marquée comme versée.")
            elif action == "rembourser":
                rembourser(paiement)
                messages.success(request, "Paiement remboursé.")
            else:
                messages.error(request, "Action inconnue.")
        except PaiementImpossible as exc:
            messages.error(request, str(exc))
        return redirect("bo_payments:detail", pk=pk)

    def _contexte(self):
        paiement = self.object
        return {
            "paiement": paiement,
            "commission": getattr(paiement, "commission", None),
            "facture": getattr(paiement, "facture", None),
        }
