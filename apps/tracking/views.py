"""Vues du module Suivi & livraison — Membre 5."""

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect
from django.views.generic import TemplateView

from apps.bookings.models import Reservation
from apps.core.mixins import AdminRequiredMixin, RoleRequiredMixin
from apps.core.roles import est_admin
from apps.core.views import ListeBackofficeView, ListeFrontView
from apps.payments.models import Paiement

from .ai import analyser_sentiment
from .forms import AvisForm, ConfirmationForm, IncidentAdminForm, IncidentForm, PositionForm, PreuveForm
from .models import Avis, Incident, ResumeTransporteur
from .services import (
    STATUTS_SUIVI,
    SuiviImpossible,
    ajouter_position,
    confirmer_livraison,
    declarer_incident,
    deposer_preuve,
    est_partie,
    est_pme_de,
    est_transporteur_de,
    get_reservation,
    laisser_avis,
    reservations_de,
)
from .tasks import calculer_resume


class SuiviView(ListeFrontView):
    model = Reservation
    roles = []
    template_name = "tracking/liste.html"
    titre = "Suivi des livraisons"
    sous_titre = "Positions, preuve de livraison, incidents et avis."

    def get_queryset(self):
        return reservations_de(self.request.user).filter(statut__in=STATUTS_SUIVI)


class SuiviDetailView(RoleRequiredMixin, TemplateView):
    """Détail d’une livraison : les formulaires postent ici (création)."""

    roles = []
    template_name = "tracking/detail.html"

    def get_queryset(self):
        return reservations_de(self.request.user).filter(statut__in=STATUTS_SUIVI)

    def get_object(self):
        return get_reservation(self.request.user, self.kwargs["pk"])

    def get(self, request, pk):
        self.object = self.get_object()
        return self.render_to_response(self._contexte())

    def post(self, request, pk):
        self.object = self.get_object()
        action = request.POST.get("action")
        if action == "position":
            return self._position(request)
        if action == "preuve":
            return self._preuve(request)
        if action == "confirmer":
            return self._confirmer(request)
        if action == "incident":
            return self._incident(request)
        if action == "avis":
            return self._avis(request)
        if action == "resume":
            return self._resume(request)
        messages.error(request, "Action inconnue.")
        return redirect("tracking:detail", pk=self.object.pk)

    def _contexte(self, **formulaires):
        reservation = self.object
        user = self.request.user
        return {
            "reservation": reservation,
            "titre": str(reservation),
            "est_pme": est_pme_de(user, reservation),
            "est_transporteur": est_transporteur_de(user, reservation),
            "positions": reservation.positions.all(),
            "preuve": getattr(reservation, "preuve", None),
            "incidents": reservation.incidents.select_related("declare_par"),
            "avis_liste": reservation.avis.select_related("auteur"),
            "mon_avis": reservation.avis.filter(auteur=user).first(),
            "resume": ResumeTransporteur.objects.filter(transporteur=reservation.trajet.transporteur).first(),
            "paiement": Paiement.objects.filter(reservation=reservation).first(),
            "form_position": formulaires.get("form_position") or PositionForm(),
            "form_preuve": formulaires.get("form_preuve") or PreuveForm(),
            "form_confirmation": formulaires.get("form_confirmation") or ConfirmationForm(),
            "form_incident": formulaires.get("form_incident") or IncidentForm(),
            "form_avis": formulaires.get("form_avis") or AvisForm(),
        }

    def _refuser_si(self, autorise):
        if not autorise:
            raise PermissionDenied

    def _erreur(self, message, **formulaires):
        messages.error(self.request, message)
        return self.render_to_response(self._contexte(**formulaires))

    def _position(self, request):
        self._refuser_si(est_transporteur_de(request.user, self.object) or est_admin(request.user))
        form = PositionForm(request.POST)
        if not form.is_valid():
            return self._erreur("Corrigez la position indiquée.", form_position=form)
        try:
            ajouter_position(self.object, request.user, form.cleaned_data["latitude"], form.cleaned_data["longitude"])
        except SuiviImpossible as exc:
            return self._erreur(str(exc), form_position=form)
        messages.success(request, "Position enregistrée. La livraison est en transit.")
        return redirect("tracking:detail", pk=self.object.pk)

    def _preuve(self, request):
        self._refuser_si(est_transporteur_de(request.user, self.object) or est_admin(request.user))
        form = PreuveForm(request.POST, request.FILES)
        if not form.is_valid():
            return self._erreur("La photo n’a pas été acceptée.", form_preuve=form)
        try:
            preuve = deposer_preuve(self.object, request.user, form.cleaned_data.get("photo"))
        except SuiviImpossible as exc:
            return self._erreur(str(exc), form_preuve=form)
        messages.success(request, f"Code de livraison : {preuve.code_otp}. Communiquez-le à la PME.")
        return redirect("tracking:detail", pk=self.object.pk)

    def _confirmer(self, request):
        self._refuser_si(est_pme_de(request.user, self.object) or est_admin(request.user))
        form = ConfirmationForm(request.POST)
        if not form.is_valid():
            return self._erreur("Indiquez le code à 6 chiffres.", form_confirmation=form)
        try:
            confirmer_livraison(self.object, request.user, form.cleaned_data["code"])
        except SuiviImpossible as exc:
            return self._erreur(str(exc), form_confirmation=form)
        messages.success(request, "Livraison confirmée. Vous pouvez payer et laisser un avis.")
        return redirect("tracking:detail", pk=self.object.pk)

    def _incident(self, request):
        self._refuser_si(est_partie(request.user, self.object))
        form = IncidentForm(request.POST)
        if not form.is_valid():
            return self._erreur("Corrigez le signalement.", form_incident=form)
        try:
            declarer_incident(self.object, request.user, form.cleaned_data["type"], form.cleaned_data["description"])
        except SuiviImpossible as exc:
            return self._erreur(str(exc), form_incident=form)
        messages.success(request, "Incident déclaré.")
        return redirect("tracking:detail", pk=self.object.pk)

    def _avis(self, request):
        self._refuser_si(est_pme_de(request.user, self.object) or est_transporteur_de(request.user, self.object))
        form = AvisForm(request.POST)
        if not form.is_valid():
            return self._erreur("Corrigez l’avis.", form_avis=form)
        try:
            laisser_avis(self.object, request.user, form.cleaned_data["note"], form.cleaned_data["commentaire"])
        except SuiviImpossible as exc:
            return self._erreur(str(exc), form_avis=form)
        messages.success(request, "Avis enregistré. Le résumé du transporteur est en cours de calcul.")
        return redirect("tracking:detail", pk=self.object.pk)

    def _resume(self, request):
        transporteur_id = self.object.trajet.transporteur_id
        autorise = est_admin(request.user) or est_partie(request.user, self.object)
        self._refuser_si(autorise)
        resume, _ = ResumeTransporteur.objects.get_or_create(transporteur_id=transporteur_id)
        resume.en_cours = True
        resume.save(update_fields=["en_cours", "updated_at"])
        calculer_resume.delay(transporteur_id)
        messages.success(request, "Analyse des avis lancée. Le résumé s’affiche dès qu’il est prêt.")
        return redirect("tracking:detail", pk=self.object.pk)


class IncidentModifierView(RoleRequiredMixin, TemplateView):
    roles = []
    template_name = "tracking/incident_formulaire.html"
    form_class = IncidentForm

    def get_queryset(self):
        return Incident.objects.select_related("reservation").filter(
            declare_par=self.request.user, statut=Incident.Statut.OUVERT
        )

    def get(self, request, pk):
        self.object = get_object_or_404(self.get_queryset(), pk=pk)
        return self.render_to_response({"incident": self.object, "form": IncidentForm(instance=self.object)})

    def post(self, request, pk):
        self.object = get_object_or_404(self.get_queryset(), pk=pk)
        form = IncidentForm(request.POST, instance=self.object)
        if not form.is_valid():
            return self.render_to_response({"incident": self.object, "form": form})
        form.save()
        messages.success(request, "Incident mis à jour.")
        return redirect("tracking:detail", pk=self.object.reservation_id)


class IncidentSupprimerView(RoleRequiredMixin, TemplateView):
    roles = []
    template_name = "tracking/incident_supprimer.html"

    def get_queryset(self):
        return Incident.objects.filter(declare_par=self.request.user, statut=Incident.Statut.OUVERT)

    def get(self, request, pk):
        self.object = get_object_or_404(self.get_queryset(), pk=pk)
        return self.render_to_response({"incident": self.object})

    def post(self, request, pk):
        incident = get_object_or_404(self.get_queryset(), pk=pk)
        reservation_id = incident.reservation_id
        incident.delete()
        messages.success(request, "Incident supprimé.")
        return redirect("tracking:detail", pk=reservation_id)


class AvisModifierView(RoleRequiredMixin, TemplateView):
    roles = []
    template_name = "tracking/avis_formulaire.html"

    def get_queryset(self):
        return Avis.objects.select_related("reservation__trajet")

    def get(self, request, pk):
        self.object = get_object_or_404(self.get_queryset(), pk=pk, auteur=request.user)
        return self.render_to_response({"avis": self.object, "form": AvisForm(instance=self.object)})

    def post(self, request, pk):
        avis = get_object_or_404(self.get_queryset(), pk=pk, auteur=request.user)
        form = AvisForm(request.POST, instance=avis)
        if not form.is_valid():
            return self.render_to_response({"avis": avis, "form": form})
        avis = form.save(commit=False)
        avis.sentiment = analyser_sentiment(avis.commentaire, avis.note)
        avis.save()
        calculer_resume.delay(avis.reservation.trajet.transporteur_id)
        messages.success(request, "Avis mis à jour.")
        return redirect("tracking:detail", pk=avis.reservation_id)


class AvisSupprimerView(RoleRequiredMixin, TemplateView):
    roles = []
    template_name = "tracking/avis_supprimer.html"

    def get(self, request, pk):
        self.object = get_object_or_404(Avis, pk=pk, auteur=request.user)
        return self.render_to_response({"avis": self.object})

    def post(self, request, pk):
        avis = get_object_or_404(Avis, pk=pk, auteur=request.user)
        reservation_id = avis.reservation_id
        transporteur_id = avis.reservation.trajet.transporteur_id
        avis.delete()
        calculer_resume.delay(transporteur_id)
        messages.success(request, "Avis supprimé.")
        return redirect("tracking:detail", pk=reservation_id)


class BackofficeIncidentView(ListeBackofficeView):
    model = Incident
    template_name = "tracking/backoffice/liste.html"
    titre = "Incidents et avis"

    def get_queryset(self):
        return Incident.objects.select_related("reservation", "declare_par")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["avis_liste"] = Avis.objects.select_related("auteur", "cible", "reservation")[:30]
        return ctx


class BackofficeIncidentDetailView(AdminRequiredMixin, TemplateView):
    template_name = "tracking/backoffice/detail.html"

    def get_queryset(self):
        return Incident.objects.select_related("reservation", "declare_par")

    def get(self, request, pk):
        self.object = get_object_or_404(self.get_queryset(), pk=pk)
        return self.render_to_response({"incident": self.object, "form": IncidentAdminForm(instance=self.object)})

    def post(self, request, pk):
        incident = get_object_or_404(self.get_queryset(), pk=pk)
        if request.POST.get("action") == "supprimer":
            incident.delete()
            messages.success(request, "Incident supprimé.")
            return redirect("bo_tracking:liste")
        form = IncidentAdminForm(request.POST, instance=incident)
        if not form.is_valid():
            return self.render_to_response({"incident": incident, "form": form})
        form.save()
        messages.success(request, "Incident mis à jour.")
        return redirect("bo_tracking:detail", pk=incident.pk)
