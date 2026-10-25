"""Vues du module Fidélité & parrainage — Membre 5."""

from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, UpdateView

from apps.core.mixins import AdminRequiredMixin
from apps.core.views import ListeBackofficeView, ListeFrontView

from .forms import CodePromoForm, ParrainageForm
from .models import CodePromo, Parrainage
from .services import ParrainageImpossible, codes_disponibles, compte_points, parrainer


class FideliteView(ListeFrontView):
    model = CodePromo
    roles = []
    template_name = "loyalty/liste.html"
    titre = "Fidélité"
    sous_titre = "Vos points, les codes promo et le parrainage."

    def get_queryset(self):
        return codes_disponibles()

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        ctx["points"] = compte_points(user)
        ctx["parrainage"] = Parrainage.objects.filter(filleul=user).select_related("parrain").first()
        ctx["filleuls"] = Parrainage.objects.filter(parrain=user).select_related("filleul")
        ctx["form_parrain"] = kwargs.get("form_parrain") or ParrainageForm()
        return ctx

    def post(self, request, *args, **kwargs):
        form = ParrainageForm(request.POST)
        if form.is_valid():
            try:
                parrainer(request.user, form.cleaned_data["email"])
            except ParrainageImpossible as exc:
                messages.error(request, str(exc))
            else:
                messages.success(request, "Parrain enregistré. Il recevra 50 points à votre premier paiement.")
            return redirect("loyalty:liste")
        self.object_list = self.get_queryset()
        return self.render_to_response(self.get_context_data(form_parrain=form))


class BackofficeCodePromoView(ListeBackofficeView):
    model = CodePromo
    template_name = "loyalty/backoffice/liste.html"
    titre = "Codes promo"

    def get_queryset(self):
        return CodePromo.objects.all()


class CodePromoCreerView(AdminRequiredMixin, CreateView):
    model = CodePromo
    form_class = CodePromoForm
    template_name = "loyalty/backoffice/formulaire.html"
    success_url = reverse_lazy("bo_loyalty:liste")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["titre"] = "Nouveau code promo"
        return ctx

    def form_valid(self, form):
        messages.success(self.request, "Code promo créé.")
        return super().form_valid(form)


class CodePromoModifierView(AdminRequiredMixin, UpdateView):
    model = CodePromo
    form_class = CodePromoForm
    template_name = "loyalty/backoffice/formulaire.html"
    success_url = reverse_lazy("bo_loyalty:liste")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["titre"] = f"Modifier {self.object.code}"
        return ctx

    def form_valid(self, form):
        messages.success(self.request, "Code promo mis à jour.")
        return super().form_valid(form)


class CodePromoSupprimerView(AdminRequiredMixin, DeleteView):
    model = CodePromo
    template_name = "loyalty/backoffice/supprimer.html"
    success_url = reverse_lazy("bo_loyalty:liste")

    def form_valid(self, form):
        messages.success(self.request, "Code promo supprimé.")
        return super().form_valid(form)
