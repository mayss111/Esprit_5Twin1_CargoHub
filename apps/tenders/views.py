"""Vues du module Appels d’offres & négociation — Membre 4.

PME          : créer / modifier / supprimer un appel d'offres, comparer les offres, retenir la meilleure.
Transporteur : voir les appels ouverts, faire / modifier / retirer son offre, obtenir un prix suggéré par l'IA.
Back-office  : tous les appels d'offres avec quelques indicateurs.
"""

import logging

from django.contrib import messages
from django.db.models import Avg, Count, Exists, OuterRef, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, DeleteView, DetailView, UpdateView

from apps.bookings.services import ReservationImpossible
from apps.core import ai
from apps.core.mixins import AdminRequiredMixin, RoleRequiredMixin
from apps.core.roles import Role
from apps.core.views import ListeBackofficeView, ListeFrontView
from apps.fleet.models import Trajet

from .ai import suggerer_prix
from .forms import AppelOffreForm, OffreForm
from .models import AppelOffre, Offre
from .services import retenir_offre
from .tasks import calculer_recommandation

logger = logging.getLogger(__name__)


def appels_visibles(user):
    """PME : ses appels. Transporteur : les appels ouverts + ceux où il a fait une offre."""
    qs = AppelOffre.objects.select_related("expedition__adresse_depart", "expedition__adresse_arrivee")
    if user.role == Role.PME:
        return qs.filter(expedition__pme=user)
    return qs.filter(
        Q(statut=AppelOffre.Statut.OUVERT, date_cloture__gt=timezone.now()) | Q(offres__transporteur=user)
    ).distinct()


# ---------------------------------------------------------------- appels d'offres


class AppelsOffresView(ListeFrontView):
    model = AppelOffre
    roles = [Role.PME, Role.TRANSPORTEUR]
    titre = "Appels d’offres"
    template_name = "tenders/liste.html"

    def get_queryset(self):
        user = self.request.user
        return (
            appels_visibles(user)
            .annotate(
                nb_offres=Count("offres", distinct=True),
                mon_offre=Exists(Offre.objects.filter(appel=OuterRef("pk"), transporteur=user)),
            )
            .order_by("date_cloture")
        )


class MesAppelsMixin(RoleRequiredMixin):
    """La PME n'accède qu'à SES appels d'offres (404 sinon)."""

    roles = [Role.PME]
    model = AppelOffre
    context_object_name = "appel"

    def get_queryset(self):
        return AppelOffre.objects.filter(expedition__pme=self.request.user)


class AppelCreerView(MesAppelsMixin, CreateView):
    form_class = AppelOffreForm
    template_name = "tenders/appel_formulaire.html"

    def get_form_kwargs(self):
        return {**super().get_form_kwargs(), "pme": self.request.user}

    def get_initial(self):
        return {"expedition": self.request.GET.get("expedition")}

    def form_valid(self, form):
        messages.success(self.request, "Appel d’offres publié : les transporteurs peuvent maintenant faire une offre.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("tenders:detail", args=[self.object.pk])


class AppelModifiableMixin(MesAppelsMixin):
    """Modifier ou supprimer n'est possible que tant qu'aucune offre n'a été reçue."""

    def dispatch(self, request, *args, **kwargs):
        # Seulement si le rôle est bon : sinon RoleRequiredMixin répond 403 (ou redirige vers la connexion).
        if request.user.is_authenticated and self.test_func():
            appel = get_object_or_404(self.get_queryset(), pk=kwargs["pk"])
            if not appel.modifiable:
                messages.error(
                    request, "Cet appel a déjà reçu des offres ou n’est plus ouvert : il ne peut plus changer."
                )
                return redirect("tenders:detail", pk=appel.pk)
        return super().dispatch(request, *args, **kwargs)


class AppelModifierView(AppelModifiableMixin, UpdateView):
    form_class = AppelOffreForm
    template_name = "tenders/appel_formulaire.html"

    def get_form_kwargs(self):
        return {**super().get_form_kwargs(), "pme": self.request.user}

    def form_valid(self, form):
        messages.success(self.request, "Appel d’offres modifié.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("tenders:detail", args=[self.object.pk])


class AppelSupprimerView(AppelModifiableMixin, DeleteView):
    template_name = "tenders/appel_supprimer.html"
    success_url = reverse_lazy("tenders:liste")

    def form_valid(self, form):
        messages.success(self.request, "Appel d’offres supprimé.")
        return super().form_valid(form)


class AppelDetailView(RoleRequiredMixin, DetailView):
    roles = [Role.PME, Role.TRANSPORTEUR]
    template_name = "tenders/detail.html"
    context_object_name = "appel"

    def get_queryset(self):
        return appels_visibles(self.request.user)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        offres = self.object.offres.select_related("transporteur", "trajet")
        if user.role == Role.PME:
            ctx["offres"] = offres
            ctx["prix_moyen"] = offres.aggregate(m=Avg("prix"))["m"]
        else:
            ctx["mon_offre"] = offres.filter(transporteur=user).first()
            ctx["nb_offres"] = offres.count()
        return ctx


class RetenirOffreView(RoleRequiredMixin, View):
    roles = [Role.PME]

    def post(self, request, pk):
        offre = get_object_or_404(Offre, pk=pk, appel__expedition__pme=request.user)
        try:
            reservation = retenir_offre(offre, par=request.user)
        except ReservationImpossible as erreur:
            messages.error(request, f"L’offre n’a pas pu être retenue : {erreur}")
            return redirect("tenders:detail", pk=offre.appel_id)
        messages.success(
            request, f"Offre de {offre.transporteur} retenue. {reservation} créée et acceptée : le contrat est prêt."
        )
        return redirect("bookings:detail", pk=reservation.pk)


class LancerRecommandationView(RoleRequiredMixin, View):
    """« Aide au choix » : la PME lance l'analyse IA des offres, calculée en arrière-plan par Celery."""

    roles = [Role.PME]

    def post(self, request, pk):
        appel = get_object_or_404(AppelOffre, pk=pk, expedition__pme=request.user)
        if appel.statut != AppelOffre.Statut.OUVERT:
            messages.error(request, "Cet appel d’offres n’est plus ouvert : il n’y a plus d’offre à comparer.")
        elif appel.offres.filter(statut=Offre.Statut.PROPOSEE).count() < 2:
            messages.error(request, "L’aide au choix compare au moins 2 offres : attendez d’autres propositions.")
        elif appel.recommandation_statut == AppelOffre.Recommandation.EN_COURS:
            messages.info(request, "Analyse déjà en cours…")
        else:
            AppelOffre.objects.filter(pk=appel.pk).update(
                recommandation_statut=AppelOffre.Recommandation.EN_COURS,
                recommandation_ia=None,
                recommandation_duree_ms=None,
            )
            try:
                calculer_recommandation.delay(appel.pk)
            except Exception:  # file Celery (Redis) indisponible
                logger.exception("Impossible de lancer l’aide au choix pour l’appel %s", appel.pk)
                AppelOffre.objects.filter(pk=appel.pk).update(recommandation_statut=AppelOffre.Recommandation.ERREUR)
                messages.error(request, "L’analyse n’a pas pu démarrer. Réessayez dans un instant.")
            else:
                messages.info(request, "Analyse en cours…")
        return redirect("tenders:detail", pk=pk)


class StatutRecommandationView(RoleRequiredMixin, View):
    """Interrogé toutes les 2 s par le navigateur tant que l'analyse est en cours (JSON)."""

    roles = [Role.PME]

    def get(self, request, pk):
        appel = get_object_or_404(AppelOffre, pk=pk, expedition__pme=request.user)
        return JsonResponse(
            {
                "statut": appel.recommandation_statut,
                "recommandation": appel.recommandation_ia,
                "duree_ms": appel.recommandation_duree_ms,
            }
        )


# ---------------------------------------------------------------- offres des transporteurs


class OffreCreerView(RoleRequiredMixin, CreateView):
    roles = [Role.TRANSPORTEUR]
    model = Offre
    form_class = OffreForm
    template_name = "tenders/offre_formulaire.html"

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and self.test_func():
            self.appel = get_object_or_404(AppelOffre, pk=kwargs["pk"])
            if not self.appel.est_ouvert:
                messages.error(request, "Cet appel d’offres est clos.")
                return redirect("tenders:liste")
            mienne = self.appel.offres.filter(transporteur=request.user).first()
            if mienne:
                messages.info(request, "Vous avez déjà fait une offre sur cet appel : vous pouvez la modifier.")
                return redirect("tenders:offre_modifier", pk=mienne.pk)
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        return {**super().get_form_kwargs(), "transporteur": self.request.user, "appel": self.appel}

    def get_context_data(self, **kwargs):
        return {**super().get_context_data(**kwargs), "appel": self.appel}

    def form_valid(self, form):
        self.appel.effacer_recommandation()  # nouvelle offre : l'aide au choix doit être refaite
        messages.success(self.request, "Offre envoyée. La PME est prévenue quand elle choisit.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("tenders:detail", args=[self.appel.pk])


class MesOffresMixin(RoleRequiredMixin):
    """Un transporteur ne touche qu'à SES offres, encore proposées, sur un appel ouvert."""

    roles = [Role.TRANSPORTEUR]
    model = Offre
    context_object_name = "offre"

    def get_queryset(self):
        return Offre.objects.filter(transporteur=self.request.user).select_related("appel")

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and self.test_func():
            offre = get_object_or_404(self.get_queryset(), pk=kwargs["pk"])
            if not offre.modifiable:
                messages.error(request, "Cette offre ne peut plus changer : l’appel est clos ou l’offre a été traitée.")
                return redirect("tenders:detail", pk=offre.appel_id)
        return super().dispatch(request, *args, **kwargs)


class OffreModifierView(MesOffresMixin, UpdateView):
    form_class = OffreForm
    template_name = "tenders/offre_formulaire.html"

    def get_form_kwargs(self):
        return {**super().get_form_kwargs(), "transporteur": self.request.user, "appel": self.object.appel}

    def get_context_data(self, **kwargs):
        return {**super().get_context_data(**kwargs), "appel": self.object.appel}

    def form_valid(self, form):
        self.object.appel.effacer_recommandation()
        messages.success(self.request, "Offre modifiée.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("tenders:detail", args=[self.object.appel_id])


class OffreRetirerView(MesOffresMixin, DeleteView):
    template_name = "tenders/offre_retirer.html"

    def form_valid(self, form):
        self.object.appel.effacer_recommandation()
        messages.success(self.request, "Offre retirée.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("tenders:detail", args=[self.object.appel_id])


class SuggestionPrixView(RoleRequiredMixin, View):
    """IA (M4) : prix suggéré pour une offre. Répond en JSON à l'appel fetch() du formulaire."""

    roles = [Role.TRANSPORTEUR]

    def post(self, request):
        appel = AppelOffre.objects.filter(pk=request.POST.get("appel") or 0).first()
        trajet = Trajet.objects.filter(pk=request.POST.get("trajet") or 0, transporteur=request.user).first()
        if appel is None or trajet is None:
            return JsonResponse({"erreur": "Choisissez d’abord un de vos trajets."}, status=400)
        if not trajet.distance_km:
            return JsonResponse(
                {"erreur": "Ce trajet n’a pas de distance renseignée : saisissez votre prix."}, status=400
            )
        try:
            resultat, duree_ms = ai.mesurer(
                suggerer_prix, distance_km=trajet.distance_km, poids_kg=float(appel.expedition.poids_total_kg)
            )
        except Exception:
            logger.exception("Suggestion de prix en échec (appel %s, trajet %s)", appel.pk, trajet.pk)
            return JsonResponse(
                {"erreur": "Le calcul du prix est indisponible pour le moment. Saisissez votre prix."}, status=503
            )
        return JsonResponse({"prix": str(resultat["prix"]), "methode": resultat["methode"], "duree_ms": duree_ms})


# ---------------------------------------------------------------- back-office


class BackofficeAppelOffreView(ListeBackofficeView):
    model = AppelOffre
    titre = "Appels d’offres"
    template_name = "tenders/backoffice/liste.html"

    def get_queryset(self):
        qs = AppelOffre.objects.select_related("expedition__pme").annotate(nb_offres=Count("offres"))
        statut = self.request.GET.get("statut")
        return qs.filter(statut=statut) if statut in AppelOffre.Statut.values else qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ouverts = AppelOffre.objects.filter(statut=AppelOffre.Statut.OUVERT)
        ctx.update(
            statuts=AppelOffre.Statut.choices,
            nb_ouverts=ouverts.count(),
            nb_sans_offre=ouverts.filter(offres__isnull=True).count(),
            prix_moyen_retenu=Offre.objects.filter(statut=Offre.Statut.RETENUE).aggregate(m=Avg("prix"))["m"],
        )
        return ctx


class BackofficeAppelDetailView(AdminRequiredMixin, DetailView):
    model = AppelOffre
    template_name = "tenders/backoffice/detail.html"
    context_object_name = "appel"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["offres"] = self.object.offres.select_related("transporteur", "trajet")
        return ctx
