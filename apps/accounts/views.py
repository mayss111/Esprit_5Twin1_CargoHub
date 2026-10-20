"""Vues du module Comptes & sécurité — Membre 1."""

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView, LogoutView
from django.urls import reverse_lazy
from django.views.generic import CreateView, TemplateView

from apps.core.views import ListeBackofficeView

from .forms import ConnexionForm, InscriptionForm
from .models import Utilisateur


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


class BackofficeUtilisateursView(ListeBackofficeView):
    model = Utilisateur
    titre = "Utilisateurs"
    colonnes = [
        ("email", "Email"),
        ("get_full_name", "Nom"),
        ("role", "Rôle"),
        ("is_active", "Actif"),
        ("date_joined", "Inscrit le"),
    ]

    def get_queryset(self):
        return Utilisateur.objects.order_by("-date_joined")
