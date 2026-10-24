"""Vues du module Contrats & documents — Membre 1.

Front-office : générer le contrat d'une réservation acceptée, le signer, le télécharger en PDF,
               déposer les documents de transport (lettre de voiture, bon de livraison…).
Back-office  : consulter et supprimer les contrats.
"""

import logging

from django.contrib import messages
from django.core.files.base import ContentFile
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import DeleteView, DetailView

from apps.bookings.models import Reservation
from apps.core.mixins import AdminRequiredMixin, RoleRequiredMixin
from apps.core.views import ListeBackofficeView, ListeFrontView

from .forms import DocumentTransportForm
from .models import Contrat, DocumentTransport
from .pdf import contrat_pdf

logger = logging.getLogger(__name__)

# Un contrat n'a de sens qu'une fois le transporteur d'accord.
STATUTS_AVEC_CONTRAT = [Reservation.Statut.ACCEPTEE, Reservation.Statut.EN_TRANSIT, Reservation.Statut.LIVREE]


def participe(user):
    """Filtre « l'utilisateur est la PME ou le transporteur de la réservation »."""
    return Q(expedition__pme=user) | Q(trajet__transporteur=user)


def reponse_pdf(contrat):
    """La version archivée si le contrat est signé par les deux parties, sinon un PDF généré à la volée."""
    if contrat.fichier:
        with contrat.fichier.open("rb") as fichier:
            contenu = fichier.read()
    else:
        contenu = contrat_pdf(contrat)
    reponse = HttpResponse(contenu, content_type="application/pdf")
    reponse["Content-Disposition"] = f'inline; filename="contrat-{contrat.reservation_id}.pdf"'
    return reponse


def contrats_de(user):
    return Contrat.objects.filter(
        Q(reservation__expedition__pme=user) | Q(reservation__trajet__transporteur=user)
    ).select_related("reservation__expedition__pme", "reservation__trajet__transporteur")


class MesContratsView(ListeFrontView):
    model = Contrat
    roles = []
    titre = "Mes contrats"
    template_name = "contracts/liste.html"

    def get_queryset(self):
        return contrats_de(self.request.user)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["reservations_sans_contrat"] = (
            Reservation.objects.filter(
                participe(self.request.user), statut__in=STATUTS_AVEC_CONTRAT, contrat__isnull=True
            )
            .select_related("expedition__adresse_depart", "expedition__adresse_arrivee")
            .distinct()
        )
        return ctx


class GenererContratView(RoleRequiredMixin, View):
    def post(self, request, reservation_id):
        reservation = get_object_or_404(
            Reservation.objects.filter(participe(request.user)).distinct(), pk=reservation_id
        )
        if reservation.statut not in STATUTS_AVEC_CONTRAT:
            messages.error(request, "Le contrat ne peut être généré qu’après l’acceptation de la réservation.")
            return redirect("contracts:liste")
        contrat, cree = Contrat.objects.get_or_create(reservation=reservation)
        messages.success(request, "Contrat généré : relisez-le puis signez-le." if cree else "Ce contrat existe déjà.")
        return redirect("contracts:detail", pk=contrat.pk)


class MesContratsMixin(RoleRequiredMixin):
    """Un utilisateur n'accède qu'aux contrats de SES réservations (404 sinon, même en changeant l'id)."""

    model = Contrat
    context_object_name = "contrat"

    def get_queryset(self):
        return contrats_de(self.request.user)


class ContratDetailView(MesContratsMixin, DetailView):
    """Détail du contrat ; le POST ajoute un document de transport à la réservation."""

    template_name = "contracts/detail.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(
            partie=self.object.partie(self.request.user),
            peut_signer=self.object.peut_signer(self.request.user),
            documents=self.object.reservation.documents.all(),
            form_document=kwargs.get("form_document") or DocumentTransportForm(),
        )
        return ctx

    def post(self, request, pk):
        self.object = self.get_object()
        form = DocumentTransportForm(request.POST, request.FILES)
        if form.is_valid():
            form.instance.reservation = self.object.reservation
            form.save()
            messages.success(request, "Document ajouté.")
            return redirect("contracts:detail", pk=pk)
        messages.error(request, "Le document n’a pas été ajouté : corrigez le formulaire.")
        return self.render_to_response(self.get_context_data(form_document=form))


class SignerContratView(MesContratsMixin, View):
    def post(self, request, pk):
        contrat = get_object_or_404(self.get_queryset(), pk=pk)
        if not contrat.peut_signer(request.user):
            messages.error(request, "Vous avez déjà signé ce contrat.")
            return redirect("contracts:detail", pk=pk)
        if request.POST.get("accepte") != "oui":
            messages.error(request, "Cochez la case pour confirmer que vous acceptez le contrat.")
            return redirect("contracts:detail", pk=pk)
        contrat.signer(request.user)
        if contrat.est_signe:
            # Archive la version signée par les deux parties : elle ne bougera plus.
            try:
                contrat.fichier.save(f"contrat-{contrat.reservation_id}.pdf", ContentFile(contrat_pdf(contrat)))
            except Exception:
                logger.exception("Archivage du contrat %s impossible", contrat.pk)
            messages.success(request, "Contrat signé par les deux parties. La version signée est archivée.")
        else:
            messages.success(request, "Votre signature est enregistrée. En attente de l’autre partie.")
        return redirect("contracts:detail", pk=pk)


class ContratPdfView(MesContratsMixin, View):
    def get(self, request, pk):
        contrat = get_object_or_404(self.get_queryset(), pk=pk)
        try:
            return reponse_pdf(contrat)
        except Exception:
            logger.exception("PDF du contrat %s impossible", contrat.pk)
            messages.error(request, "Le PDF n’a pas pu être généré. Réessayez plus tard.")
            return redirect("contracts:detail", pk=pk)


class ContratSupprimerView(MesContratsMixin, DeleteView):
    template_name = "contracts/supprimer.html"
    success_url = reverse_lazy("contracts:liste")

    def form_valid(self, form):
        if not self.object.sans_signature:
            messages.error(self.request, "Un contrat déjà signé ne peut plus être supprimé.")
            return redirect("contracts:detail", pk=self.object.pk)
        messages.success(self.request, "Contrat supprimé.")
        return super().form_valid(form)


class DocumentSupprimerView(RoleRequiredMixin, View):
    def post(self, request, pk):
        document = get_object_or_404(
            DocumentTransport.objects.filter(
                Q(reservation__expedition__pme=request.user) | Q(reservation__trajet__transporteur=request.user)
            ),
            pk=pk,
        )
        contrat = getattr(document.reservation, "contrat", None)
        document.fichier.delete(save=False)
        document.delete()
        messages.success(request, "Document supprimé.")
        return redirect("contracts:detail", pk=contrat.pk) if contrat else redirect("contracts:liste")


# ---------------------------------------------------------------- back-office


class BackofficeContratView(ListeBackofficeView):
    model = Contrat
    titre = "Contrats"
    template_name = "contracts/backoffice/liste.html"

    def get_queryset(self):
        qs = Contrat.objects.select_related("reservation__expedition__pme", "reservation__trajet__transporteur")
        filtre = self.request.GET.get("signature")
        if filtre == "signes":
            qs = qs.filter(signe_par_pme_le__isnull=False, signe_par_transporteur_le__isnull=False)
        elif filtre == "en_attente":
            qs = qs.filter(Q(signe_par_pme_le__isnull=True) | Q(signe_par_transporteur_le__isnull=True))
        return qs


class BackofficeContratDetailView(AdminRequiredMixin, DetailView):
    model = Contrat
    template_name = "contracts/backoffice/detail.html"
    context_object_name = "contrat"


class BackofficeContratPdfView(AdminRequiredMixin, View):
    def get(self, request, pk):
        return reponse_pdf(get_object_or_404(Contrat, pk=pk))


class BackofficeContratSupprimerView(AdminRequiredMixin, DeleteView):
    model = Contrat
    template_name = "contracts/backoffice/supprimer.html"
    context_object_name = "contrat"
    success_url = reverse_lazy("bo_contracts:liste")

    def form_valid(self, form):
        messages.success(self.request, "Contrat supprimé.")
        return super().form_valid(form)
