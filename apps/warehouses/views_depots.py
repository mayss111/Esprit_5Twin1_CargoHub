"""Pages de réservation de dépôt, côté PME et administrateur."""

from decimal import Decimal

from django.contrib import messages
from django.db.models import DecimalField, ExpressionWrapper, F, OuterRef, Q, Subquery, Sum
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import View
from django.views.generic import DetailView, ListView

from apps.core.mixins import AdminRequiredMixin, RoleRequiredMixin
from apps.core.roles import Role
from apps.warehouses.forms import AnnulationDepotForm
from apps.warehouses.models import CreneauDepot, Entrepot, MouvementColis
from apps.warehouses.services.reservation import (
    annuler,
    depot_pour_affichage,
    expedition_de,
    expeditions_eligibles,
    lister_creneaux,
    message_reservation,
    parse_date,
    reserver,
    volume_expedition,
)

VOLUME = Coalesce(
    Sum(
        ExpressionWrapper(
            F("expedition__articles__volume_m3") * F("expedition__articles__quantite"),
            output_field=DecimalField(max_digits=14, decimal_places=3),
        )
    ),
    Decimal("0"),
)


def queryset_reservations():
    entrees = MouvementColis.objects.filter(creneau_id=OuterRef("pk"), type=MouvementColis.Type.ENTREE).order_by("date")
    sorties = MouvementColis.objects.filter(creneau_id=OuterRef("pk"), type=MouvementColis.Type.SORTIE).order_by(
        "-date"
    )
    return (
        CreneauDepot.objects.select_related(
            "entrepot",
            "expedition__pme",
            "expedition__adresse_depart",
            "expedition__adresse_arrivee",
        )
        .annotate(
            volume_m3=VOLUME,
            entree_le=Subquery(entrees.values("date")[:1]),
            sortie_le=Subquery(sorties.values("date")[:1]),
        )
        .order_by("-created_at")
    )


def filtrer_reservations(request, queryset, avec_entrepot=False):
    recherche = (request.GET.get("q") or "").strip()[:40]
    if recherche:
        queryset = queryset.filter(Q(reference__icontains=recherche) | Q(expedition__reference__icontains=recherche))
    statut = (request.GET.get("statut") or "").strip()
    if statut in CreneauDepot.Statut.values:
        queryset = queryset.filter(statut=statut)
    elif statut:
        queryset = queryset.none()
    texte_date = (request.GET.get("date") or "").strip()
    jour, erreur_date = parse_date(texte_date)
    if texte_date and erreur_date:
        queryset = queryset.none()
    elif jour is not None:
        queryset = queryset.filter(debut__date=jour)
    entrepot = ""
    email = ""
    if avec_entrepot:
        entrepot = (request.GET.get("entrepot") or "").strip()
        if entrepot.isdigit():
            queryset = queryset.filter(entrepot_id=int(entrepot))
        elif entrepot:
            queryset = queryset.none()
        email = (request.GET.get("email") or "").strip()[:254]
        if email:
            queryset = queryset.filter(expedition__pme__email__icontains=email)
    return queryset, {
        "q": recherche,
        "email": email,
        "statut": statut if statut in CreneauDepot.Statut.values else "",
        "date": jour.isoformat() if jour else "",
        "entrepot": entrepot if entrepot.isdigit() else "",
    }


def _contexte_formulaire(request, entrepot, erreur=""):
    source = request.POST if request.method == "POST" else request.GET
    expeditions = expeditions_eligibles(request.user)
    expedition, message = expedition_de(request.user, source.get("expedition"))
    depot = depot_pour_affichage(expedition) if expedition else None
    jour, erreur_date = parse_date(source.get("date"))
    creneaux = []
    volume = None
    if expedition and depot:
        erreur = erreur or "Cette expédition a déjà un dépôt réservé."
    elif expedition and jour and not erreur_date:
        volume = volume_expedition(expedition)
        creneaux, erreur_liste = lister_creneaux(entrepot, expedition, jour)
        if not creneaux:
            erreur = erreur or erreur_liste
    elif expedition:
        volume = volume_expedition(expedition)
    if not erreur:
        erreur = message or erreur_date
    return {
        "entrepot": entrepot,
        "expeditions": expeditions,
        "expedition": None if message else expedition,
        "jour": jour,
        "creneaux": creneaux,
        "volume": volume,
        "erreur": erreur,
        "creneau_choisi": (source.get("creneau") or "").strip(),
        "fin_reservation": (source.get("fin_reservation") or "").strip(),
        "depot_existant": depot,
        "aujourd_hui": timezone.localdate(),
    }


class ReserverDepotView(RoleRequiredMixin, View):
    roles = [Role.PME]
    template_name = "warehouses/reserver.html"

    def get(self, request, pk):
        entrepot = get_object_or_404(Entrepot, pk=pk, actif=True)
        return render(request, self.template_name, _contexte_formulaire(request, entrepot))

    def post(self, request, pk):
        entrepot = get_object_or_404(Entrepot, pk=pk, actif=True)
        jour, _erreur = parse_date(request.POST.get("date"))
        creneau, erreur = reserver(
            request.user,
            entrepot.pk,
            request.POST.get("expedition"),
            jour,
            request.POST.get("creneau"),
            request.POST.get("fin_reservation"),
        )
        if creneau is not None:
            messages.success(request, message_reservation(creneau))
            return redirect("warehouses:depot", pk=creneau.pk)
        return render(request, self.template_name, _contexte_formulaire(request, entrepot, erreur))


class MesDepotsView(RoleRequiredMixin, ListView):
    roles = [Role.PME]
    template_name = "warehouses/mes_depots.html"
    context_object_name = "reservations"
    paginate_by = 10

    def get_queryset(self):
        queryset = queryset_reservations().filter(expedition__pme=self.request.user)
        queryset, self.filtre = filtrer_reservations(self.request, queryset)
        return queryset

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        contexte["filtre"] = getattr(self, "filtre", {})
        contexte["statuts"] = CreneauDepot.Statut.choices
        return contexte


class DetailDepotView(RoleRequiredMixin, DetailView):
    roles = [Role.PME]
    template_name = "warehouses/depot_detail.html"
    context_object_name = "reservation"

    def get_queryset(self):
        return queryset_reservations().filter(expedition__pme=self.request.user)

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        contexte["mouvements"] = self.object.mouvements.select_related("scanne_par").order_by("date")
        return contexte


class AnnulerDepotView(RoleRequiredMixin, View):
    roles = [Role.PME]
    template_name = "warehouses/depot_annuler.html"

    def get(self, request, pk):
        reservation = get_object_or_404(queryset_reservations().filter(expedition__pme=request.user), pk=pk)
        return render(request, self.template_name, {"reservation": reservation})

    def post(self, request, pk):
        get_object_or_404(CreneauDepot.objects.filter(expedition__pme=request.user), pk=pk)
        reservation, erreur = annuler(pk, request.user)
        if erreur:
            messages.error(request, erreur)
            return redirect("warehouses:depot", pk=pk)
        messages.success(request, f"Le dépôt {reservation.reference} est annulé. Il reste dans l'historique.")
        return redirect("warehouses:depot", pk=reservation.pk)


class BackofficeReservationsView(AdminRequiredMixin, ListView):
    template_name = "warehouses/backoffice_reservations.html"
    context_object_name = "reservations"
    paginate_by = 20

    def get_queryset(self):
        queryset, self.filtre = filtrer_reservations(self.request, queryset_reservations(), avec_entrepot=True)
        return queryset

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        contexte["filtre"] = getattr(self, "filtre", {})
        contexte["statuts"] = CreneauDepot.Statut.choices
        contexte["entrepots"] = Entrepot.objects.order_by("nom", "ville")
        contexte["recherche"] = any(self.request.GET.get(nom) for nom in ("q", "email", "entrepot", "date", "statut"))
        return contexte


class BackofficeDetailReservationView(AdminRequiredMixin, DetailView):
    template_name = "warehouses/backoffice_reservation.html"
    context_object_name = "reservation"

    def get_queryset(self):
        return queryset_reservations()


class BackofficeAnnulerReservationView(AdminRequiredMixin, View):
    template_name = "warehouses/backoffice_reservation_annuler.html"

    def get(self, request, pk):
        reservation = get_object_or_404(queryset_reservations(), pk=pk)
        return render(
            request,
            self.template_name,
            {"reservation": reservation, "formulaire": AnnulationDepotForm()},
        )

    def post(self, request, pk):
        reservation = get_object_or_404(queryset_reservations(), pk=pk)
        formulaire = AnnulationDepotForm(request.POST)
        if not formulaire.is_valid():
            return render(
                request,
                self.template_name,
                {"reservation": reservation, "formulaire": formulaire},
            )
        reservation, erreur = annuler(
            pk,
            request.user,
            motif=formulaire.cleaned_data["motif"],
            admin=True,
        )
        if erreur:
            messages.error(request, erreur)
            if reservation is None:
                reservation = get_object_or_404(queryset_reservations(), pk=pk)
            return render(
                request,
                self.template_name,
                {"reservation": reservation, "formulaire": formulaire},
            )
        messages.success(request, f"Le dépôt {reservation.reference} est annulé.")
        return redirect("bo_warehouses:reservation", pk=reservation.pk)
