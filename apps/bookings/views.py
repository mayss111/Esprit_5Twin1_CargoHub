"""Vues du module Matching & réservations — Membre 4.

PME          : trouver un camion compatible, réserver, suivre et annuler ses réservations.
Transporteur : accepter ou refuser les demandes reçues.
Back-office  : toutes les réservations (filtres, détail, annulation pour litige).

Les changements de statut passent TOUJOURS par services.changer_statut() (capacité du camion, historique).
"""

from django.contrib import messages
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from django.views.generic import DetailView, ListView, TemplateView

from apps.core.mixins import AdminRequiredMixin, RoleRequiredMixin
from apps.core.roles import Role
from apps.core.views import ListeBackofficeView, ListeFrontView
from apps.fleet.models import Trajet
from apps.shipments.models import Expedition

from .forms import AnnulationLitigeForm, FiltreReservationsForm
from .models import Reservation
from .services import EXPEDITION_VIDE, ReservationImpossible, changer_statut, reserver, trajets_compatibles

EN_COURS = [Reservation.Statut.EN_ATTENTE, Reservation.Statut.ACCEPTEE]


def reservations_de(user):
    """Réservations où l'utilisateur est la PME ou le transporteur (une autre réservation → 404)."""
    return (
        Reservation.objects.filter(Q(expedition__pme=user) | Q(trajet__transporteur=user))
        .select_related(
            "expedition__pme", "expedition__adresse_depart", "expedition__adresse_arrivee", "trajet__transporteur"
        )
        .prefetch_related("trajet__etapes")  # « Sfax → Tunis, via Monastir » sans une requête par ligne
    )


def statut_demande(request):
    """Statut choisi dans le filtre ?statut=…, ignoré s'il n'existe pas."""
    statut = request.GET.get("statut", "")
    return statut if statut in Reservation.Statut.values else ""


# ---------------------------------------------------------------- PME : trouver un camion et réserver


class ExpeditionsAReserverView(RoleRequiredMixin, ListView):
    roles = [Role.PME]
    template_name = "bookings/trouver.html"
    context_object_name = "expeditions"

    def get_queryset(self):
        return (
            Expedition.objects.filter(pme=self.request.user, statut=Expedition.Statut.PUBLIEE)
            .select_related("adresse_depart", "adresse_arrivee")
            .annotate(demandes=Count("reservations", filter=Q(reservations__statut__in=EN_COURS)))
            .order_by("date_souhaitee")
        )


class CamionsCompatiblesView(RoleRequiredMixin, TemplateView):
    roles = [Role.PME]
    template_name = "bookings/camions.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        expedition = get_object_or_404(
            Expedition.objects.select_related("adresse_depart", "adresse_arrivee"),
            pk=self.kwargs["pk"],
            pme=self.request.user,
        )
        publiee = expedition.statut == Expedition.Statut.PUBLIEE
        vide = expedition.poids_total_kg <= 0
        ctx.update(
            expedition=expedition,
            publiee=publiee,
            vide=vide,
            message_vide=EXPEDITION_VIDE,
            resultats=trajets_compatibles(expedition) if publiee and not vide else [],
            deja_demandes=set(expedition.reservations.filter(statut__in=EN_COURS).values_list("trajet_id", flat=True)),
        )
        return ctx


class ReserverView(RoleRequiredMixin, View):
    roles = [Role.PME]

    def post(self, request, pk, trajet_id):
        expedition = get_object_or_404(Expedition, pk=pk, pme=request.user)
        trajet = get_object_or_404(Trajet, pk=trajet_id, statut=Trajet.Statut.OUVERT)
        if expedition.statut != Expedition.Statut.PUBLIEE:
            messages.error(request, "Seule une expédition publiée peut être réservée.")
        elif expedition.poids_total_kg <= 0:
            messages.error(request, EXPEDITION_VIDE)
        elif expedition.reservations.filter(trajet=trajet, statut__in=EN_COURS).exists():
            messages.warning(request, "Vous avez déjà demandé une place sur ce trajet.")
        else:
            reservation = reserver(expedition, trajet)
            messages.success(
                request, f"Demande envoyée au transporteur ({reservation}). Vous serez prévenu de sa réponse."
            )
            return redirect("bookings:detail", pk=reservation.pk)
        return redirect("bookings:camions", pk=pk)


# ---------------------------------------------------------------- PME et transporteur : mes réservations


class MesReservationsView(ListeFrontView):
    model = Reservation
    roles = [Role.PME, Role.TRANSPORTEUR]
    titre = "Mes réservations"
    template_name = "bookings/liste.html"

    def get_queryset(self):
        qs = reservations_de(self.request.user)
        if statut := statut_demande(self.request):
            qs = qs.filter(statut=statut)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(statuts=Reservation.Statut.choices, statut_actif=statut_demande(self.request))
        return ctx


class ReservationDetailView(RoleRequiredMixin, DetailView):
    roles = [Role.PME, Role.TRANSPORTEUR]
    template_name = "bookings/detail.html"
    context_object_name = "reservation"

    def get_queryset(self):
        return reservations_de(self.request.user)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        ctx.update(
            historique=self.object.historique.select_related("par"),
            est_pme=self.object.expedition.pme_id == user.pk,
            est_transporteur=self.object.trajet.transporteur_id == user.pk,
        )
        return ctx


class AnnulerReservationView(RoleRequiredMixin, DetailView):
    """GET : page de confirmation. POST : annulation (la place est rendue au camion si elle était acceptée)."""

    roles = [Role.PME]
    template_name = "bookings/annuler.html"
    context_object_name = "reservation"

    def get_queryset(self):
        return Reservation.objects.filter(expedition__pme=self.request.user)

    def post(self, request, pk):
        reservation = self.get_object()
        try:
            changer_statut(reservation, Reservation.Statut.ANNULEE, par=request.user)
        except ReservationImpossible:
            messages.error(request, "Cette réservation ne peut plus être annulée.")
        else:
            messages.success(request, f"{reservation} annulée.")
        return redirect("bookings:detail", pk=pk)


# ---------------------------------------------------------------- transporteur : demandes reçues


class DemandesRecuesView(ListeFrontView):
    model = Reservation
    roles = [Role.TRANSPORTEUR]
    titre = "Demandes reçues"
    template_name = "bookings/demandes.html"

    def get_queryset(self):
        return reservations_de(self.request.user).filter(
            trajet__transporteur=self.request.user, statut=Reservation.Statut.EN_ATTENTE
        )


class RepondreDemandeView(RoleRequiredMixin, View):
    roles = [Role.TRANSPORTEUR]
    ACTIONS = {"accepter": Reservation.Statut.ACCEPTEE, "refuser": Reservation.Statut.REFUSEE}

    def post(self, request, pk):
        reservation = get_object_or_404(Reservation, pk=pk, trajet__transporteur=request.user)
        nouveau = self.ACTIONS.get(request.POST.get("action"))
        if nouveau is None:
            messages.error(request, "Action inconnue.")
        else:
            try:
                changer_statut(reservation, nouveau, par=request.user)
            except ReservationImpossible as erreur:
                messages.error(request, f"Impossible : {erreur}.")
            else:
                verbe = "acceptée" if nouveau == Reservation.Statut.ACCEPTEE else "refusée"
                messages.success(request, f"{reservation} {verbe}. La PME est prévenue.")
        if request.POST.get("retour") == "detail":
            return redirect("bookings:detail", pk=pk)
        return redirect("bookings:demandes")


# ---------------------------------------------------------------- back-office


class BackofficeReservationView(ListeBackofficeView):
    model = Reservation
    titre = "Réservations"
    template_name = "bookings/backoffice/liste.html"

    def get_queryset(self):
        qs = Reservation.objects.select_related("expedition__pme", "trajet__transporteur")
        self.filtres = FiltreReservationsForm(self.request.GET or None)
        if not self.filtres.is_valid():
            return qs
        f = self.filtres.cleaned_data
        if f["statut"]:
            qs = qs.filter(statut=f["statut"])
        if f["pme"]:
            qs = qs.filter(expedition__pme=f["pme"])
        if f["transporteur"]:
            qs = qs.filter(trajet__transporteur=f["transporteur"])
        if f["du"]:
            qs = qs.filter(created_at__date__gte=f["du"])
        if f["au"]:
            qs = qs.filter(created_at__date__lte=f["au"])
        if q := f["q"].strip():
            recherche = (
                Q(expedition__reference__icontains=q)
                | Q(expedition__pme__email__icontains=q)
                | Q(trajet__transporteur__email__icontains=q)
                | Q(trajet__ville_depart__icontains=q)
                | Q(trajet__ville_arrivee__icontains=q)
            )
            if q.lstrip("#").isdigit():
                recherche |= Q(pk=int(q.lstrip("#")))
            qs = qs.filter(recherche)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["filtres"] = self.filtres
        return ctx


class BackofficeReservationDetailView(AdminRequiredMixin, DetailView):
    model = Reservation
    template_name = "bookings/backoffice/detail.html"
    context_object_name = "reservation"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(
            historique=self.object.historique.select_related("par"),
            form_litige=kwargs.get("form_litige") or AnnulationLitigeForm(),
        )
        return ctx


class BackofficeAnnulerLitigeView(BackofficeReservationDetailView):
    """POST uniquement : si le motif manque, la page détail est réaffichée avec l'erreur sous le champ."""

    http_method_names = ["post"]

    def post(self, request, pk):
        reservation = self.object = self.get_object()
        form = AnnulationLitigeForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Indiquez le motif de l’annulation (10 caractères minimum).")
            return self.render_to_response(self.get_context_data(form_litige=form))
        try:
            changer_statut(
                reservation,
                Reservation.Statut.ANNULEE,
                par=request.user,
                motif=f"Litige : {form.cleaned_data['motif']}",
            )
        except ReservationImpossible:
            messages.error(request, "Cette réservation ne peut plus être annulée (déjà en transit, livrée ou close).")
        else:
            messages.success(request, f"{reservation} annulée pour litige. La PME est prévenue.")
        return redirect("bo_bookings:detail", pk=pk)
