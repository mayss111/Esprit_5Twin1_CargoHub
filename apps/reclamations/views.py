from datetime import datetime

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from apps.core.mixins import AdminRequiredMixin, RoleRequiredMixin
from apps.core.roles import Role

from .forms import ReclamationForm, TraitementReclamationForm
from .models import Reclamation


class MesReclamationsView(RoleRequiredMixin, ListView):
    model = Reclamation
    roles = [Role.PME, Role.TRANSPORTEUR]
    template_name = "reclamations/liste.html"
    context_object_name = "reclamations"
    paginate_by = None

    def get_queryset(self):
        if self.request.user.role == Role.TRANSPORTEUR:
            acces = Q(auteur=self.request.user) | Q(expedition__reservations__trajet__transporteur=self.request.user)
        elif self.request.user.role == Role.PME:
            acces = Q(auteur=self.request.user) | Q(expedition__pme=self.request.user)
        else:
            acces = Q(auteur=self.request.user)
        queryset = Reclamation.objects.filter(acces).distinct().select_related("expedition", "auteur")
        if recherche := self.request.GET.get("q", "").strip():
            queryset = queryset.filter(Q(reference__icontains=recherche) | Q(titre__icontains=recherche))
        if statut := self.request.GET.get("statut"):
            queryset = queryset.filter(statut=statut)
        if type_reclamation := self.request.GET.get("type"):
            queryset = queryset.filter(type_reclamation=type_reclamation)
        for key, lookup in (("date_debut", "created_at__date__gte"), ("date_fin", "created_at__date__lte")):
            valeur = self.request.GET.get(key)
            if valeur:
                try:
                    queryset = queryset.filter(**{lookup: datetime.strptime(valeur, "%Y-%m-%d").date()})
                except ValueError:
                    pass
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["recherche"] = self.request.GET.get("q", "")
        context["statuts"] = Reclamation.Statut.choices
        context["types"] = Reclamation.Type.choices
        context["filtres"] = self.request.GET
        context["reclamations_concernees"] = self.object_list.exclude(auteur=self.request.user)
        context["reclamations"] = self.object_list.filter(auteur=self.request.user)
        return context


class ReclamationCreerView(RoleRequiredMixin, CreateView):
    model = Reclamation
    form_class = ReclamationForm
    roles = [Role.PME, Role.TRANSPORTEUR]
    template_name = "reclamations/formulaire.html"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        form.instance.auteur = self.request.user
        response = super().form_valid(form)
        messages.success(self.request, "Votre réclamation a été enregistrée et est en attente de traitement.")
        return response

    def get_success_url(self):
        return reverse("reclamations:detail", args=[self.object.pk])


class MesReclamationsMixin(LoginRequiredMixin):
    model = Reclamation
    context_object_name = "reclamation"

    def get_queryset(self):
        if self.request.user.role == Role.TRANSPORTEUR:
            acces = Q(auteur=self.request.user) | Q(expedition__reservations__trajet__transporteur=self.request.user)
        elif self.request.user.role == Role.PME:
            acces = Q(auteur=self.request.user) | Q(expedition__pme=self.request.user)
        else:
            acces = Q(auteur=self.request.user)
        return Reclamation.objects.filter(acces).distinct().select_related("expedition", "auteur", "assigne_a")


class ReclamationDetailView(MesReclamationsMixin, DetailView):
    template_name = "reclamations/detail.html"


class ReclamationModifierView(MesReclamationsMixin, UpdateView):
    form_class = ReclamationForm
    template_name = "reclamations/formulaire.html"

    def get_queryset(self):
        return super().get_queryset().filter(auteur=self.request.user, statut__in=[Reclamation.Statut.EN_ATTENTE, Reclamation.Statut.INFOS])

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, "Votre réclamation a été mise à jour.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("reclamations:detail", args=[self.object.pk])


class ReclamationAnnulerView(MesReclamationsMixin, View):
    def post(self, request, pk):
        reclamation = get_object_or_404(self.get_queryset().filter(auteur=request.user), pk=pk)
        if not reclamation.annulable_par_auteur:
            messages.error(request, "Cette réclamation ne peut plus être annulée.")
        else:
            reclamation.statut = Reclamation.Statut.ANNULEE
            reclamation.save(update_fields=["statut", "updated_at"])
            messages.success(request, "Votre réclamation a été annulée.")
        return redirect("reclamations:detail", pk=pk)


class BackofficeReclamationsView(AdminRequiredMixin, ListView):
    model = Reclamation
    template_name = "reclamations/backoffice/liste.html"
    context_object_name = "reclamations"
    paginate_by = 25

    def get_queryset(self):
        queryset = Reclamation.objects.select_related("auteur", "expedition", "assigne_a")
        recherche = self.request.GET.get("q", "").strip()
        if recherche:
            queryset = queryset.filter(Q(reference__icontains=recherche) | Q(titre__icontains=recherche))
        if statut := self.request.GET.get("statut"):
            queryset = queryset.filter(statut=statut)
        if type_reclamation := self.request.GET.get("type"):
            queryset = queryset.filter(type_reclamation=type_reclamation)
        for key, lookup in (("date_debut", "created_at__date__gte"), ("date_fin", "created_at__date__lte")):
            valeur = self.request.GET.get(key)
            if valeur:
                try:
                    queryset = queryset.filter(**{lookup: datetime.strptime(valeur, "%Y-%m-%d").date()})
                except ValueError:
                    pass
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["statuts"] = Reclamation.Statut.choices
        context["types"] = Reclamation.Type.choices
        context["filtres"] = self.request.GET
        return context


class BackofficeReclamationDetailView(AdminRequiredMixin, UpdateView):
    model = Reclamation
    form_class = TraitementReclamationForm
    template_name = "reclamations/backoffice/detail.html"
    context_object_name = "reclamation"

    def get_queryset(self):
        return Reclamation.objects.select_related("auteur", "expedition", "assigne_a")

    def form_valid(self, form):
        if form.cleaned_data.get("statut") == Reclamation.Statut.RESOLUE:
            form.instance.resolue_le = timezone.now()
        elif form.cleaned_data.get("statut") not in {Reclamation.Statut.RESOLUE, Reclamation.Statut.REJETEE}:
            form.instance.resolue_le = None
        if not form.instance.assigne_a_id and form.cleaned_data.get("statut") != Reclamation.Statut.EN_ATTENTE:
            form.instance.assigne_a = self.request.user
        response = super().form_valid(form)
        messages.success(self.request, "La réclamation a été mise à jour.")
        return response

    def get_success_url(self):
        return reverse("bo_reclamations:detail", args=[self.object.pk])

