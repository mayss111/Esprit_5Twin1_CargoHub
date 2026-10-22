"""Pages PME du module Expéditions : liste, création, détail, modification, annulation."""

from datetime import date

from django.contrib import messages
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import View
from django.views.generic import DetailView, ListView

from apps.core.mixins import AdminRequiredMixin, RoleRequiredMixin
from apps.core.roles import Role

from .forms import SaisieExpedition
from .models import Expedition


def filtrer_expeditions(queryset, request):
    """Recherche par référence, statut, villes et date. Les paramètres vides sont ignorés."""
    reference = request.GET.get("q", "").strip()
    if reference:
        queryset = queryset.filter(reference__icontains=reference)

    statut = request.GET.get("statut", "").strip()
    if statut in Expedition.Statut.values:
        queryset = queryset.filter(statut=statut)

    depart = request.GET.get("depart", "").strip()
    if depart:
        queryset = queryset.filter(adresse_depart__ville__icontains=depart)

    arrivee = request.GET.get("arrivee", "").strip()
    if arrivee:
        queryset = queryset.filter(adresse_arrivee__ville__icontains=arrivee)

    date_brute = request.GET.get("date", "").strip()
    if date_brute:
        try:
            queryset = queryset.filter(date_souhaitee=date.fromisoformat(date_brute))
        except ValueError:
            pass
    return queryset


class ExpeditionAccesMixin(RoleRequiredMixin):
    """Une PME ne voit que ses propres expéditions. Les autres obtiennent une 404."""

    roles = [Role.PME]

    def get_queryset(self):
        return (
            Expedition.objects.filter(pme=self.request.user)
            .select_related("adresse_depart", "adresse_arrivee", "pme")
            .prefetch_related("articles")
        )

    def get_expedition(self, pk):
        return get_object_or_404(self.get_queryset(), pk=pk)


class MesExpeditionsView(ExpeditionAccesMixin, ListView):
    template_name = "shipments/liste.html"
    context_object_name = "expeditions"
    paginate_by = 20
    historique = False
    titre = "Mes expéditions"
    sous_titre = "Vos demandes d'envoi et leur statut."

    def get_queryset(self):
        queryset = super().get_queryset()
        if self.historique:
            aujourdhui = timezone.localdate()
            queryset = queryset.filter(
                Q(statut__in=[Expedition.Statut.RESERVEE, Expedition.Statut.LIVREE, Expedition.Statut.ANNULEE])
                | Q(date_souhaitee__lt=aujourdhui)
            )
        return filtrer_expeditions(queryset, self.request)

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        params = self.request.GET.copy()
        params.pop("page", None)
        get = self.request.GET
        contexte.update(
            titre=self.titre,
            sous_titre=self.sous_titre,
            historique=self.historique,
            statuts=Expedition.Statut.choices,
            filtres=params.urlencode(),
            filtre={
                "q": get.get("q", ""),
                "statut": get.get("statut", ""),
                "depart": get.get("depart", ""),
                "arrivee": get.get("arrivee", ""),
                "date": get.get("date", ""),
            },
        )
        return contexte


class HistoriqueExpeditionsView(MesExpeditionsView):
    historique = True
    titre = "Historique des expéditions"
    sous_titre = "Expéditions passées, réservées, livrées ou annulées."


class CreerExpeditionView(ExpeditionAccesMixin, View):
    template_name = "shipments/formulaire.html"

    def get(self, request):
        return render(request, self.template_name, self._contexte(SaisieExpedition(pme=request.user)))

    def post(self, request):
        publier = "publier" in request.POST
        saisie = SaisieExpedition(request.POST, pme=request.user, publier=publier)
        if saisie.is_valid():
            expedition = saisie.save()
            if publier:
                messages.success(request, f"L'expédition {expedition.reference} est publiée.")
            else:
                messages.success(request, f"Le brouillon {expedition.reference} est enregistré.")
            return redirect("shipments:detail", pk=expedition.pk)
        messages.error(request, "Corrigez les champs signalés avant d'enregistrer.")
        return render(request, self.template_name, self._contexte(saisie, publier))

    def _contexte(self, saisie, publier=False):
        return {"saisie": saisie, "publier": publier, "expedition": None, "titre": "Nouvelle expédition"}


class DetailExpeditionView(ExpeditionAccesMixin, DetailView):
    template_name = "shipments/detail.html"
    context_object_name = "expedition"


class ModifierExpeditionView(ExpeditionAccesMixin, View):
    template_name = "shipments/formulaire.html"

    def get(self, request, pk):
        expedition = self.get_expedition(pk)
        if not expedition.peut_etre_modifiee():
            messages.error(request, "Cette expédition ne peut plus être modifiée.")
            return redirect("shipments:detail", pk=expedition.pk)
        saisie = SaisieExpedition(expedition=expedition)
        return render(request, self.template_name, self._contexte(saisie, expedition))

    def post(self, request, pk):
        expedition = self.get_expedition(pk)
        if not expedition.peut_etre_modifiee():
            messages.error(request, "Cette expédition ne peut plus être modifiée.")
            return redirect("shipments:detail", pk=expedition.pk)
        publier = "publier" in request.POST
        saisie = SaisieExpedition(request.POST, expedition=expedition, publier=publier)
        if saisie.is_valid():
            saisie.save()
            messages.success(request, f"L'expédition {expedition.reference} est mise à jour.")
            return redirect("shipments:detail", pk=expedition.pk)
        messages.error(request, "Corrigez les champs signalés avant d'enregistrer.")
        return render(request, self.template_name, self._contexte(saisie, expedition, publier))

    def _contexte(self, saisie, expedition, publier=False):
        return {
            "saisie": saisie,
            "publier": publier,
            "expedition": expedition,
            "titre": f"Modifier {expedition.reference}",
        }


class AnnulerExpeditionView(ExpeditionAccesMixin, View):
    def get(self, request, pk):
        expedition = self.get_expedition(pk)
        if not expedition.peut_etre_annulee():
            messages.error(request, "Cette expédition ne peut pas être annulée.")
            return redirect("shipments:detail", pk=expedition.pk)
        return render(
            request,
            "shipments/confirmer.html",
            {
                "expedition": expedition,
                "titre": "Annuler l'expédition",
                "question": f"Annuler {expedition.reference} ? Elle restera dans l'historique.",
                "action": "Annuler l'expédition",
            },
        )

    def post(self, request, pk):
        expedition = self.get_expedition(pk)
        if not expedition.peut_etre_annulee():
            messages.error(request, "Cette expédition ne peut pas être annulée.")
            return redirect("shipments:detail", pk=expedition.pk)
        expedition.statut = Expedition.Statut.ANNULEE
        expedition.save(update_fields=["statut", "updated_at"])
        messages.success(request, f"L'expédition {expedition.reference} est annulée.")
        return redirect("shipments:detail", pk=expedition.pk)


class SupprimerExpeditionView(ExpeditionAccesMixin, View):
    def get(self, request, pk):
        expedition = self.get_expedition(pk)
        if not expedition.peut_etre_supprimee():
            messages.error(request, "Seul un brouillon peut être supprimé.")
            return redirect("shipments:detail", pk=expedition.pk)
        return render(
            request,
            "shipments/confirmer.html",
            {
                "expedition": expedition,
                "titre": "Supprimer le brouillon",
                "question": f"Supprimer définitivement {expedition.reference} ? Cette action est irréversible.",
                "action": "Supprimer le brouillon",
            },
        )

    def post(self, request, pk):
        expedition = self.get_expedition(pk)
        if not expedition.peut_etre_supprimee():
            messages.error(request, "Seul un brouillon peut être supprimé.")
            return redirect("shipments:detail", pk=expedition.pk)
        reference = expedition.reference
        expedition.delete()
        messages.success(request, f"Le brouillon {reference} est supprimé.")
        return redirect("shipments:liste")


class BackofficeExpeditionView(AdminRequiredMixin, ListView):
    """Toutes les expéditions de la plateforme, avec recherche et filtres."""

    template_name = "shipments/backoffice_liste.html"
    context_object_name = "expeditions"
    paginate_by = 20

    def get_queryset(self):
        queryset = Expedition.objects.select_related(
            "pme", "pme__profil_pme", "adresse_depart", "adresse_arrivee"
        ).prefetch_related("articles")
        queryset = filtrer_expeditions(queryset, self.request)
        pme = self.request.GET.get("pme", "").strip()
        if pme:
            queryset = queryset.filter(Q(pme__email__icontains=pme) | Q(pme__profil_pme__raison_sociale__icontains=pme))
        return queryset

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        params = self.request.GET.copy()
        params.pop("page", None)
        get = self.request.GET
        contexte.update(
            statuts=Expedition.Statut.choices,
            filtres=params.urlencode(),
            filtre={
                "q": get.get("q", ""),
                "statut": get.get("statut", ""),
                "date": get.get("date", ""),
                "pme": get.get("pme", ""),
            },
        )
        return contexte


class BackofficeDetailExpeditionView(AdminRequiredMixin, DetailView):
    template_name = "shipments/backoffice_detail.html"
    context_object_name = "expedition"

    def get_queryset(self):
        return Expedition.objects.select_related(
            "pme", "pme__profil_pme", "adresse_depart", "adresse_arrivee"
        ).prefetch_related("articles")
