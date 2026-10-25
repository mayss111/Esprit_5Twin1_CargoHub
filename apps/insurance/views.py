"""CRUD des sinistres, avec filtrage d'accès côté serveur."""

from datetime import datetime

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from apps.core.mixins import AdminRequiredMixin, RoleRequiredMixin
from apps.core.roles import Role

from .forms import PieceJustificativeForm, SinistreForm, TraitementSinistreForm
from .models import PieceJustificative, Sinistre


class MesSinistresView(RoleRequiredMixin, ListView):
    model = Sinistre
    roles = [Role.PME, Role.TRANSPORTEUR]
    template_name = "insurance/liste.html"
    context_object_name = "sinistres"
    paginate_by = None

    def get_queryset(self):
        if self.request.user.role == Role.TRANSPORTEUR:
            acces = Q(auteur=self.request.user) | Q(expedition__reservations__trajet__transporteur=self.request.user)
        elif self.request.user.role == Role.PME:
            acces = Q(auteur=self.request.user) | Q(expedition__pme=self.request.user)
        else:
            acces = Q(auteur=self.request.user)
        return Sinistre.objects.filter(acces).distinct().select_related("expedition", "police")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["sinistres_concernes"] = self.object_list.exclude(auteur=self.request.user)
        context["sinistres"] = self.object_list.filter(auteur=self.request.user)
        return context


class SinistreCreerView(RoleRequiredMixin, CreateView):
    model = Sinistre
    form_class = SinistreForm
    roles = [Role.PME, Role.TRANSPORTEUR]
    template_name = "insurance/formulaire.html"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        form.instance.auteur = self.request.user
        form.instance.statut = Sinistre.Statut.A_VERIFIER
        response = super().form_valid(form)
        for fichier in form.cleaned_data.get("justificatifs", []):
            PieceJustificative.objects.create(sinistre=self.object, fichier=fichier)
        messages.success(self.request, "Votre sinistre a été déclaré et transmis pour vérification.")
        return response

    def get_success_url(self):
        return reverse("insurance:detail", args=[self.object.pk])


class MesSinistresMixin(LoginRequiredMixin):
    model = Sinistre
    context_object_name = "sinistre"

    def get_queryset(self):
        if self.request.user.role == Role.TRANSPORTEUR:
            acces = Q(auteur=self.request.user) | Q(expedition__reservations__trajet__transporteur=self.request.user)
        elif self.request.user.role == Role.PME:
            acces = Q(auteur=self.request.user) | Q(expedition__pme=self.request.user)
        else:
            acces = Q(auteur=self.request.user)
        return Sinistre.objects.filter(acces).distinct().select_related("expedition", "auteur", "assigne_a")


class SinistreDetailView(MesSinistresMixin, DetailView):
    template_name = "insurance/detail.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["justificatif_form"] = PieceJustificativeForm()
        return context


class SinistreModifierView(MesSinistresMixin, UpdateView):
    form_class = SinistreForm
    template_name = "insurance/formulaire.html"

    def get_queryset(self):
        return super().get_queryset().filter(auteur=self.request.user, statut__in=[Sinistre.Statut.A_VERIFIER, Sinistre.Statut.DOCUMENTS])

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        response = super().form_valid(form)
        for fichier in form.cleaned_data.get("justificatifs", []):
            PieceJustificative.objects.create(sinistre=self.object, fichier=fichier)
        messages.success(self.request, "Votre sinistre a été mis à jour.")
        return response

    def get_success_url(self):
        return reverse("insurance:detail", args=[self.object.pk])


class PieceJustificativeSupprimerView(MesSinistresMixin, View):
    def post(self, request, pk):
        sinistre = get_object_or_404(self.get_queryset().filter(auteur=request.user), pk=pk)
        piece = get_object_or_404(PieceJustificative, pk=request.POST.get("piece"), sinistre=sinistre)
        if not sinistre.modifiable_par_auteur:
            messages.error(request, "Les justificatifs ne peuvent plus être modifiés à ce stade.")
        else:
            piece.delete()
            messages.success(request, "Justificatif supprimé.")
        return redirect("insurance:detail", pk=pk)


class SinistreSupprimerView(MesSinistresMixin, View):
    def post(self, request, pk):
        sinistre = get_object_or_404(self.get_queryset().filter(auteur=request.user), pk=pk)
        if sinistre.statut != Sinistre.Statut.A_VERIFIER:
            messages.error(request, "Un sinistre déjà traité ne peut pas être supprimé.")
        else:
            sinistre.delete()
            messages.success(request, "Sinistre supprimé.")
            return redirect("insurance:liste")
        return redirect("insurance:detail", pk=pk)


class BackofficeSinistreView(AdminRequiredMixin, ListView):
    model = Sinistre
    template_name = "insurance/backoffice/liste.html"
    context_object_name = "sinistres"
    paginate_by = 25

    def get_queryset(self):
        queryset = Sinistre.objects.select_related("auteur", "expedition", "police", "assigne_a")
        recherche = self.request.GET.get("q", "").strip()
        if recherche:
            queryset = queryset.filter(Q(reference__icontains=recherche) | Q(titre__icontains=recherche))
        if statut := self.request.GET.get("statut"):
            queryset = queryset.filter(statut=statut)
        if type_sinistre := self.request.GET.get("type"):
            queryset = queryset.filter(type_sinistre=type_sinistre)
        for key, lookup in (("date_debut", "date_incident__gte"), ("date_fin", "date_incident__lte")):
            valeur = self.request.GET.get(key)
            if valeur:
                try:
                    queryset = queryset.filter(**{lookup: datetime.strptime(valeur, "%Y-%m-%d").date()})
                except ValueError:
                    pass
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(statuts=Sinistre.Statut.choices, types=Sinistre.Type.choices, filtres=self.request.GET)
        return context


class BackofficeSinistreDetailView(AdminRequiredMixin, UpdateView):
    model = Sinistre
    form_class = TraitementSinistreForm
    template_name = "insurance/backoffice/detail.html"
    context_object_name = "sinistre"

    def get_queryset(self):
        return Sinistre.objects.select_related("auteur", "expedition", "police", "assigne_a").prefetch_related("pieces")

    def form_valid(self, form):
        if form.cleaned_data.get("statut") in {Sinistre.Statut.ACCEPTE, Sinistre.Statut.REFUSE, Sinistre.Statut.CLOTURE}:
            form.instance.resolu_le = form.instance.resolu_le or timezone.now()
        if not form.instance.assigne_a_id and form.cleaned_data.get("statut") != Sinistre.Statut.A_VERIFIER:
            form.instance.assigne_a = self.request.user
        response = super().form_valid(form)
        messages.success(self.request, "Le sinistre a été mis à jour.")
        return response

    def get_success_url(self):
        return reverse("bo_insurance:detail", args=[self.object.pk])
