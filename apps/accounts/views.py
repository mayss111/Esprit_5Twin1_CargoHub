"""Vues du module Comptes & sécurité — Membre 1."""

from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth import views as auth_views
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView, LogoutView
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.generic import CreateView, DeleteView, DetailView, TemplateView, UpdateView

from apps.core.mixins import AdminRequiredMixin
from apps.core.roles import Role
from apps.core.views import ListeBackofficeView
from .reliability import score_fiabilite

from .forms import (
    BackofficeUtilisateurForm,
    ConnexionForm,
    InscriptionForm,
    ProfilPMEForm,
    ProfilTransporteurForm,
    ProfilUtilisateurForm,
    ValidationTransporteurForm,
)
from .models import ProfilPME, ProfilTransporteur, Utilisateur


class InscriptionView(CreateView):
    form_class = InscriptionForm
    template_name = "accounts/inscription.html"
    success_url = reverse_lazy("core:accueil")

    def form_valid(self, form):
        reponse = super().form_valid(form)
        login(self.request, self.object)
        messages.success(self.request, "Bienvenue sur CargoHub !")
        return reponse


class ConnexionView(LoginView):
    form_class = ConnexionForm
    template_name = "accounts/connexion.html"
    redirect_authenticated_user = True


class DeconnexionView(LogoutView):
    pass


class ProfilView(LoginRequiredMixin, TemplateView):
    template_name = "accounts/profil.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.user.role == Role.ADMIN:
            comptes = Utilisateur.objects.filter(role__in=[Role.PME, Role.TRANSPORTEUR]).order_by("role", "email")
            context["fiabilites_admin"] = [(compte, score_fiabilite(compte)) for compte in comptes]
            context["fiabilite"] = None
        else:
            context["fiabilite"] = score_fiabilite(self.request.user)
            context["fiabilites_admin"] = []
        return context


def profil_de(user):
    """Profil PME ou transporteur de l'utilisateur (None pour un administrateur)."""
    if user.role == Role.PME:
        return ProfilPME.objects.get_or_create(utilisateur=user, defaults={"raison_sociale": user.get_full_name()})[0]
    if user.role == Role.TRANSPORTEUR:
        return ProfilTransporteur.objects.get_or_create(utilisateur=user)[0]
    return None


class ModifierProfilView(LoginRequiredMixin, View):
    """Modifie le compte et, selon le rôle, le profil PME ou le profil transporteur (documents)."""

    template_name = "accounts/profil_modifier.html"

    def formulaires(self, data=None, files=None):
        user = self.request.user
        profil = profil_de(user)
        form_profil = None
        if isinstance(profil, ProfilPME):
            form_profil = ProfilPMEForm(data, instance=profil, prefix="profil")
        elif isinstance(profil, ProfilTransporteur):
            form_profil = ProfilTransporteurForm(data, files, instance=profil, prefix="profil")
        return ProfilUtilisateurForm(data, files, instance=user, prefix="compte"), form_profil

    def get(self, request):
        form, form_profil = self.formulaires()
        return render(request, self.template_name, {"form": form, "form_profil": form_profil})

    def post(self, request):
        form, form_profil = self.formulaires(request.POST, request.FILES)
        if form.is_valid() and (form_profil is None or form_profil.is_valid()):
            form.save()
            if form_profil is not None:
                form_profil.save()
            messages.success(request, "Votre profil a été mis à jour.")
            return redirect("accounts:profil")
        messages.error(request, "Corrigez les erreurs signalées dans le formulaire.")
        return render(request, self.template_name, {"form": form, "form_profil": form_profil})


class DesactiverCompteView(LoginRequiredMixin, TemplateView):
    """Le compte est désactivé (et non supprimé) pour garder l'historique des réservations et paiements."""

    template_name = "accounts/compte_desactiver.html"

    def post(self, request):
        user = request.user
        user.is_active = False
        user.save(update_fields=["is_active"])
        logout(request)
        messages.success(request, "Votre compte a été désactivé. Contactez le support pour le réactiver.")
        return redirect("core:accueil")


# ---------------------------------------------------------------- mot de passe oublié


class MotDePasseOublieView(auth_views.PasswordResetView):
    template_name = "accounts/mot_de_passe_oublie.html"
    email_template_name = "accounts/emails/reinitialisation.txt"
    subject_template_name = "accounts/emails/reinitialisation_sujet.txt"
    success_url = reverse_lazy("accounts:mot_de_passe_envoye")


class MotDePasseEnvoyeView(auth_views.PasswordResetDoneView):
    template_name = "accounts/mot_de_passe_envoye.html"


class ReinitialiserMotDePasseView(auth_views.PasswordResetConfirmView):
    template_name = "accounts/reinitialiser.html"
    success_url = reverse_lazy("accounts:reinitialisation_terminee")


class ReinitialisationTermineeView(auth_views.PasswordResetCompleteView):
    template_name = "accounts/reinitialisation_terminee.html"


# ---------------------------------------------------------------- back-office


class BackofficeUtilisateursView(ListeBackofficeView):
    model = Utilisateur
    titre = "Utilisateurs"
    template_name = "accounts/backoffice/liste.html"

    def get_queryset(self):
        qs = Utilisateur.objects.select_related("profil_transporteur").order_by("-date_joined")
        if role := self.request.GET.get("role"):
            qs = qs.filter(role=role)
        if self.request.GET.get("a_valider"):
            qs = qs.filter(profil_transporteur__statut_validation=ProfilTransporteur.Statut.EN_ATTENTE)
        if recherche := self.request.GET.get("q", "").strip():
            qs = qs.filter(
                Q(email__icontains=recherche) | Q(first_name__icontains=recherche) | Q(last_name__icontains=recherche)
            )
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["roles"] = Role.choices
        for utilisateur in ctx["object_list"]:
            utilisateur.fiabilite = (
                score_fiabilite(utilisateur)
                if utilisateur.role in {Role.PME, Role.TRANSPORTEUR}
                else None
            )
        return ctx


class BackofficeUtilisateurDetailView(AdminRequiredMixin, DetailView):
    model = Utilisateur
    template_name = "accounts/backoffice/detail.html"
    context_object_name = "utilisateur"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        profil = getattr(self.object, "profil_transporteur", None) if self.object.role == Role.TRANSPORTEUR else None
        ctx["profil_transporteur"] = profil
        ctx["fiabilite"] = (
            score_fiabilite(self.object)
            if self.object.role in {Role.PME, Role.TRANSPORTEUR}
            else None
        )
        if profil:
            ctx["form_validation"] = ValidationTransporteurForm(instance=profil)
        return ctx


class BackofficeUtilisateurModifierView(AdminRequiredMixin, UpdateView):
    model = Utilisateur
    form_class = BackofficeUtilisateurForm
    template_name = "accounts/backoffice/formulaire.html"
    context_object_name = "utilisateur"

    def form_valid(self, form):
        if form.instance == self.request.user and not form.cleaned_data["is_active"]:
            form.add_error("is_active", "Vous ne pouvez pas désactiver votre propre compte.")
            return self.form_invalid(form)
        messages.success(self.request, "Utilisateur mis à jour.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("bo_accounts:detail", args=[self.object.pk])


class BackofficeValiderTransporteurView(AdminRequiredMixin, View):
    """Valide ou refuse les documents d'un transporteur (POST uniquement)."""

    def post(self, request, pk):
        profil = get_object_or_404(ProfilTransporteur, utilisateur_id=pk)
        form = ValidationTransporteurForm(request.POST, instance=profil)
        if form.is_valid():
            form.save()
            messages.success(request, f"Transporteur : {profil.get_statut_validation_display().lower()}.")
        else:
            messages.error(request, "Décision invalide.")
        return redirect("bo_accounts:detail", pk=pk)


class BackofficeUtilisateurSupprimerView(AdminRequiredMixin, DeleteView):
    model = Utilisateur
    template_name = "accounts/backoffice/supprimer.html"
    context_object_name = "utilisateur"
    success_url = reverse_lazy("bo_accounts:liste")

    def form_valid(self, form):
        if self.object == self.request.user:
            messages.error(self.request, "Vous ne pouvez pas supprimer votre propre compte.")
            return redirect("bo_accounts:detail", pk=self.object.pk)
        messages.success(self.request, f"Le compte {self.object.email} a été supprimé.")
        return super().form_valid(form)
