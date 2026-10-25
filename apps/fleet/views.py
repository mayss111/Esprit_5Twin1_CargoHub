"""Vues du module Flotte & trajets — Membre 3.

Transporteur : gérer ses véhicules (documents, conformité), publier / modifier / annuler ses trajets,
               voir son impact CO₂, télécharger son certificat vert, utiliser le planificateur IA.
Back-office  : tous les véhicules (valider / refuser) et tous les trajets.
"""

from datetime import timedelta

from django.contrib import messages
from django.db.models import Count, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, DeleteView, FormView, UpdateView

from apps.core.mixins import AdminRequiredMixin, RoleRequiredMixin
from apps.core.roles import Role
from apps.core.views import ListeBackofficeView, ListeFrontView

from .ai import recommander_vehicules
from .forms import DocumentVehiculeForm, PlanificationForm, TrajetForm, VehiculeForm
from .models import DocumentVehicule, Trajet, Vehicule
from .services import bilan_co2, generer_certificat_vert

# ---------------------------------------------------------------- véhicules


class MesVehiculesView(ListeFrontView):
    model = Vehicule
    roles = [Role.TRANSPORTEUR]
    titre = "Mes véhicules"
    template_name = "fleet/vehicules.html"

    def get_queryset(self):
        return Vehicule.objects.filter(transporteur=self.request.user).prefetch_related("documents")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["types_documents"] = DocumentVehicule.Type.choices
        ctx["demain"] = timezone.localdate() + timedelta(days=1)
        return ctx


class MesVehiculesMixin(RoleRequiredMixin):
    """Un transporteur ne touche qu'à SES véhicules (404 sinon)."""

    roles = [Role.TRANSPORTEUR]
    model = Vehicule
    context_object_name = "vehicule"
    success_url = reverse_lazy("fleet:vehicules")

    def get_queryset(self):
        return Vehicule.objects.filter(transporteur=self.request.user)


class VehiculeCreerView(MesVehiculesMixin, CreateView):
    form_class = VehiculeForm
    template_name = "fleet/vehicule_formulaire.html"

    def form_valid(self, form):
        form.instance.transporteur = self.request.user
        messages.success(self.request, "Véhicule ajouté. Ajoutez sa carte grise et son assurance.")
        return super().form_valid(form)


class VehiculeModifierView(MesVehiculesMixin, UpdateView):
    form_class = VehiculeForm
    template_name = "fleet/vehicule_formulaire.html"

    def form_valid(self, form):
        messages.success(self.request, "Véhicule modifié.")
        return super().form_valid(form)


class VehiculeSupprimerView(MesVehiculesMixin, DeleteView):
    template_name = "fleet/vehicule_supprimer.html"

    def form_valid(self, form):
        if self.object.trajets.exists():  # Trajet.vehicule est protégé (PROTECT)
            messages.error(self.request, "Ce véhicule a des trajets : il ne peut pas être supprimé.")
            return redirect(self.success_url)
        messages.success(self.request, "Véhicule supprimé.")
        return super().form_valid(form)


class DocumentAjouterView(MesVehiculesMixin, View):
    """Carte grise ou assurance : remplace l'ancien document du même type puis recalcule la conformité."""

    def post(self, request, pk):
        vehicule = get_object_or_404(self.get_queryset(), pk=pk)
        form = DocumentVehiculeForm(request.POST, request.FILES, vehicule=vehicule)
        if not form.is_valid():
            for erreurs in form.errors.values():
                for erreur in erreurs:
                    messages.error(request, f"{vehicule.immatriculation} : {erreur}")
            return redirect(self.success_url)
        DocumentVehicule.objects.filter(vehicule=vehicule, type=form.cleaned_data["type"]).delete()
        form.save()
        vehicule.recalculer_conformite()
        messages.success(request, f"{form.instance.get_type_display()} enregistrée, conformité mise à jour.")
        return redirect(self.success_url)


class CertificatVertView(MesVehiculesMixin, View):
    """Certificat vert PDF du véhicule pour l'année en cours."""

    def get(self, request, pk):
        vehicule = get_object_or_404(self.get_queryset(), pk=pk)
        fin = timezone.localdate()
        contenu, _bilan = generer_certificat_vert(request.user, fin.replace(month=1, day=1), fin, vehicule=vehicule)
        reponse = HttpResponse(contenu, content_type="application/pdf")
        reponse["Content-Disposition"] = f'attachment; filename="certificat-vert-{vehicule.immatriculation}.pdf"'
        return reponse


# ---------------------------------------------------------------- trajets


class MesTrajetsView(ListeFrontView):
    model = Trajet
    roles = [Role.TRANSPORTEUR]
    titre = "Mes trajets"
    template_name = "fleet/liste.html"  # tableau + carte Leaflet des itinéraires

    def get_queryset(self):
        return (
            Trajet.objects.filter(transporteur=self.request.user).select_related("vehicule").prefetch_related("etapes")
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["trajets_carte"] = [
            {
                "id": t.pk,
                "ville_depart": t.ville_depart,
                "ville_arrivee": t.ville_arrivee,
                "type_vehicule": t.vehicule.type,
            }
            for t in ctx["object_list"]
        ]
        return ctx


class MesTrajetsMixin(RoleRequiredMixin):
    """Un transporteur ne touche qu'à SES trajets (404 sinon)."""

    roles = [Role.TRANSPORTEUR]
    model = Trajet
    form_class = TrajetForm
    context_object_name = "trajet"
    template_name = "fleet/trajet_formulaire.html"
    success_url = reverse_lazy("fleet:liste")

    def get_queryset(self):
        return Trajet.objects.filter(transporteur=self.request.user)

    def get_form_kwargs(self):
        return {**super().get_form_kwargs(), "transporteur": self.request.user}


class TrajetCreerView(MesTrajetsMixin, CreateView):
    def form_valid(self, form):
        messages.success(self.request, "Trajet publié : les PME peuvent maintenant le réserver.")
        return super().form_valid(form)


class TrajetModifierView(MesTrajetsMixin, UpdateView):
    def dispatch(self, request, *args, **kwargs):
        # Seulement si le rôle est bon : sinon RoleRequiredMixin répond 403 (ou redirige vers la connexion).
        if request.user.is_authenticated and self.test_func():
            trajet = get_object_or_404(self.get_queryset(), pk=kwargs["pk"])
            if trajet.statut not in (Trajet.Statut.OUVERT, Trajet.Statut.COMPLET):
                messages.error(request, "Ce trajet est parti, terminé ou annulé : il ne peut plus changer.")
                return redirect(self.success_url)
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        messages.success(self.request, "Trajet modifié.")
        return super().form_valid(form)


class TrajetAnnulerView(MesTrajetsMixin, View):
    """Annulation logique : le trajet reste visible, avec le statut « Annulé »."""

    def post(self, request, pk):
        trajet = get_object_or_404(self.get_queryset(), pk=pk)
        if trajet.statut not in (Trajet.Statut.OUVERT, Trajet.Statut.COMPLET):
            messages.error(request, "Seul un trajet qui n’est pas encore parti peut être annulé.")
        elif trajet.reservations.filter(statut__in=Trajet.STATUTS_RESERVES).exists():
            messages.error(request, "Ce trajet a des réservations acceptées : annulez-les d’abord.")
        else:
            trajet.statut = Trajet.Statut.ANNULE
            trajet.save(update_fields=["statut", "updated_at"])
            messages.success(request, "Trajet annulé.")
        return redirect(self.success_url)


# ---------------------------------------------------------------- impact & IA


class ImpactView(ListeFrontView):
    """Bilan CO₂ de chaque véhicule du transporteur (trajets terminés)."""

    model = Vehicule
    roles = [Role.TRANSPORTEUR]
    titre = "Impact écologique"
    template_name = "fleet/impact.html"

    def get_queryset(self):
        return Vehicule.objects.filter(transporteur=self.request.user)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        ctx["bilans"] = [(v, bilan_co2(user, vehicule=v)) for v in ctx["object_list"]]
        ctx["total"] = bilan_co2(user)
        return ctx


class PlanificateurView(RoleRequiredMixin, FormView):
    """IA (M3) : classe les véhicules du transporteur pour une mission prévisionnelle."""

    roles = [Role.TRANSPORTEUR]
    form_class = PlanificationForm
    template_name = "fleet/planificateur.html"

    def form_valid(self, form):
        donnees = form.cleaned_data
        recommandations = recommander_vehicules(
            transporteur=self.request.user,
            poids_kg=donnees["poids_kg"],
            volume_m3=donnees["volume_m3"],
            distance_km=donnees["distance_km"],
            date_depart=donnees["date_depart"],
        )
        return self.render_to_response(
            self.get_context_data(form=form, mission=donnees, recommandations=recommandations)
        )


# ---------------------------------------------------------------- back-office


class BackofficeVehiculeView(ListeBackofficeView):
    model = Vehicule
    titre = "Véhicules"
    template_name = "fleet/backoffice/liste.html"

    def get_queryset(self):
        qs = Vehicule.objects.select_related("transporteur").prefetch_related("documents")
        statut = self.request.GET.get("statut")
        return qs.filter(statut=statut) if statut in Vehicule.Statut.values else qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(
            statuts=Vehicule.Statut.choices,
            **Vehicule.objects.aggregate(
                nb_vehicules=Count("pk"),
                nb_non_conformes=Count("pk", filter=Q(statut=Vehicule.Statut.NON_CONFORME)),
            ),
            nb_trajets_ouverts=Trajet.objects.filter(statut=Trajet.Statut.OUVERT).count(),
        )
        return ctx


class BackofficeVehiculeDecisionView(AdminRequiredMixin, View):
    """Valider (ACTIF) ou refuser (NON_CONFORME, avec un motif) un véhicule."""

    def post(self, request, pk):
        vehicule = get_object_or_404(Vehicule, pk=pk)
        if request.POST.get("decision") == "valider":
            vehicule.statut, vehicule.conforme, vehicule.motif_non_conformite = Vehicule.Statut.ACTIF, True, ""
        else:
            motif = request.POST.get("motif", "").strip() or "Refusé par l’administrateur"
            vehicule.statut, vehicule.conforme, vehicule.motif_non_conformite = (
                Vehicule.Statut.NON_CONFORME,
                False,
                motif[:255],
            )
        vehicule.save(update_fields=["statut", "conforme", "motif_non_conformite", "updated_at"])
        messages.success(request, f"Véhicule {vehicule.immatriculation} : {vehicule.get_statut_display()}.")
        return redirect("bo_fleet:liste")


class BackofficeTrajetView(ListeBackofficeView):
    model = Trajet
    titre = "Trajets"
    colonnes = [
        ("ville_depart", "Départ"),
        ("ville_arrivee", "Arrivée"),
        ("date_depart", "Date"),
        ("transporteur", "Transporteur"),
        ("vehicule", "Véhicule"),
        ("capacite_dispo_kg", "Place libre (kg)"),
        ("statut", "Statut"),
    ]

    def get_queryset(self):
        return Trajet.objects.select_related("vehicule", "transporteur")
