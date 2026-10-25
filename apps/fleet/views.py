"""Vues Django (serveur) du module Flotte & trajets — Membre 3.

Ces pages complètent l'API REST (`api.py`) utilisée par le SPA React :
listes du front/back-office, formulaires CRUD, téléversement de documents,
annulation de trajet et téléchargement du certificat vert (session navigateur,
sans jeton JWT).
"""

from datetime import date

from django.contrib import messages
from django.db.models import Max
from django.db.models.deletion import ProtectedError
from django.forms import Select
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, DeleteView, FormView, UpdateView

from apps.core.mixins import RoleRequiredMixin
from apps.core.roles import Role, est_admin
from apps.core.views import ListeBackofficeView, ListeFrontView

from .ai import recommander_vehicules
from .forms import PlanificationIAForm
from .models import DocumentVehicule, Trajet, Vehicule
from .services import bilan_co2, generer_certificat_vert
from .upload_validation import erreur_fichier_vehicule


def _styliser_formulaire(form):
    for champ in form.fields.values():
        classe = "form-select" if isinstance(champ.widget, Select) else "form-control"
        champ.widget.attrs["class"] = f"{champ.widget.attrs.get('class', '')} {classe}".strip()
    return form


# ----------------------------------------------------------------- front-office
class OptimiseurIATransportView(RoleRequiredMixin, FormView):
    """Classe les véhicules du transporteur pour une mission prévisionnelle."""

    roles = [Role.TRANSPORTEUR]
    form_class = PlanificationIAForm
    template_name = "fleet/optimiseur_ia.html"

    def form_valid(self, form):
        donnees = form.cleaned_data
        recommandations = recommander_vehicules(
            transporteur=self.request.user,
            poids_kg=donnees["poids_kg"],
            volume_m3=donnees["volume_m3"],
            distance_km=donnees["distance_km"],
            date_depart=donnees["date_depart"],
        )
        contexte = self.get_context_data(form=form)
        contexte.update(mission=donnees, recommandations=recommandations)
        return self.render_to_response(contexte)


class MesTrajetsView(ListeFrontView):
    model = Trajet
    roles = [Role.TRANSPORTEUR]
    titre = "Mes trajets"
    sous_titre = "Les trajets que vous proposez et leur place libre."
    template_name = "fleet/liste_trajets.html"  # liste + carte Leaflet des itinéraires
    colonnes = [
        ("ville_depart", "Départ"),
        ("ville_arrivee", "Arrivée"),
        ("date_depart", "Date"),
        ("capacite_dispo_kg", "Place libre (kg)"),
        ("statut", "Statut"),
    ]

    def get_queryset(self):
        return Trajet.objects.filter(transporteur=self.request.user).select_related("vehicule")

    def get_context_data(self, **kwargs):
        import json

        contexte = super().get_context_data(**kwargs)
        trajets = list(self.get_queryset())
        contexte["trajets"] = trajets
        # Sert la carte Leaflet (templates/fleet/liste_trajets.html)
        contexte["trajets_json"] = json.dumps(
            [
                {
                    "id": t.pk,
                    "ville_depart": t.ville_depart,
                    "ville_arrivee": t.ville_arrivee,
                    "type_vehicule": t.vehicule.type,
                }
                for t in trajets
            ],
            ensure_ascii=False,
        )
        return contexte


class MesVehiculesView(ListeFrontView):
    model = Vehicule
    roles = [Role.TRANSPORTEUR]
    titre = "Mes véhicules"
    sous_titre = "Vos camions et leur capacité."
    template_name = "fleet/liste_vehicules.html"  # documents + actions (certificat, suppression)
    colonnes = [
        ("immatriculation", "Immatriculation"),
        ("type", "Type"),
        ("capacite_kg", "Capacité (kg)"),
        ("statut", "Statut"),
        ("motif_non_conformite", "Conformité"),
    ]

    def get_queryset(self):
        return Vehicule.objects.filter(transporteur=self.request.user).prefetch_related("documents")

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        contexte["vehicules"] = self.get_queryset()
        return contexte


class CreerVehiculeView(CreateView):
    """Formulaire d'ajout d'un véhicule côté transporteur."""

    model = Vehicule
    fields = ["type", "immatriculation", "capacite_kg", "capacite_m3"]
    template_name = "fleet/formulaire_vehicule.html"

    def get_form(self, form_class=None):
        return _styliser_formulaire(super().get_form(form_class))

    def form_valid(self, form):
        form.instance.transporteur = self.request.user
        messages.success(self.request, "Véhicule ajouté. Il est en attente de validation par l'administrateur.")
        return super().form_valid(form)

    def get_success_url(self):
        return "/flotte/vehicules/"


class ModifierVehiculeView(UpdateView):
    model = Vehicule
    fields = ["type", "immatriculation", "capacite_kg", "capacite_m3"]
    template_name = "fleet/formulaire_vehicule.html"

    def get_form(self, form_class=None):
        return _styliser_formulaire(super().get_form(form_class))

    def form_valid(self, form):
        vehicule = form.save(commit=False)
        capacites_utilisees = vehicule.trajets.filter(
            statut__in=[Trajet.Statut.PUBLIE, Trajet.Statut.COMPLET, Trajet.Statut.EN_COURS]
        ).aggregate(poids=Max("capacite_totale_kg"), volume=Max("capacite_totale_m3"))
        if capacites_utilisees["poids"] and vehicule.capacite_kg < capacites_utilisees["poids"]:
            form.add_error("capacite_kg", "La capacité ne peut pas être inférieure à celle d'un trajet actif.")
        if capacites_utilisees["volume"] and vehicule.capacite_m3 < capacites_utilisees["volume"]:
            form.add_error("capacite_m3", "Le volume ne peut pas être inférieur à celui d'un trajet actif.")
        if form.errors:
            return self.form_invalid(form)
        messages.success(self.request, "Véhicule modifié.")
        return super().form_valid(form)

    def get_queryset(self):
        return Vehicule.objects.filter(transporteur=self.request.user)

    def get_success_url(self):
        return "/flotte/vehicules/"


class SupprimerVehiculeView(DeleteView):
    model = Vehicule
    template_name = "fleet/confirmer_suppression.html"

    def get_queryset(self):
        return Vehicule.objects.filter(transporteur=self.request.user)

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        if self.object.trajets.exists():
            messages.error(request, "Ce véhicule est lié à des trajets et ne peut pas être supprimé.")
            return redirect(self.get_success_url())
        try:
            return super().post(request, *args, **kwargs)
        except ProtectedError:
            messages.error(request, "Ce véhicule est encore utilisé et ne peut pas être supprimé.")
            return redirect(self.get_success_url())

    def get_success_url(self):
        return "/flotte/vehicules/"


class AjouterDocumentView(View):
    """Téléversement d'une carte grise ou d'une assurance (multipart)."""

    def post(self, request, pk):
        vehicule = get_object_or_404(Vehicule, pk=pk, transporteur=request.user)
        fichier = request.FILES.get("fichier")
        type_doc = request.POST.get("type")
        expiration = request.POST.get("date_expiration")
        try:
            date_expiration = date.fromisoformat(expiration) if expiration else None
        except ValueError:
            date_expiration = None
        if not fichier or not date_expiration or type_doc not in DocumentVehicule.Type.values:
            messages.error(request, "Fichier, type et date d'expiration sont obligatoires.")
            return redirect("/flotte/vehicules/")
        if date_expiration <= timezone.localdate():
            messages.error(request, "La date d'expiration du document doit être dans le futur.")
            return redirect("/flotte/vehicules/")
        erreur = erreur_fichier_vehicule(fichier)
        if erreur:
            messages.error(request, erreur)
            return redirect("/flotte/vehicules/")
        DocumentVehicule.objects.filter(vehicule=vehicule, type=type_doc).delete()
        DocumentVehicule.objects.create(
            vehicule=vehicule, type=type_doc, fichier=fichier, date_expiration=date_expiration
        )
        vehicule.recalculer_conformite()
        messages.success(request, "Document enregistré, conformité mise à jour.")
        return redirect("/flotte/vehicules/")


class PublierTrajetView(CreateView):
    """Publication d'un trajet : capacité plafonnée au véhicule, conformité exigée."""

    model = Trajet
    fields = [
        "vehicule",
        "ville_depart",
        "ville_arrivee",
        "date_depart",
        "capacite_dispo_kg",
        "capacite_dispo_m3",
        "prix_indicatif",
    ]
    template_name = "fleet/formulaire_trajet.html"

    def get_form(self, form_class=None):
        form = _styliser_formulaire(super().get_form(form_class))
        form.fields["vehicule"].queryset = Vehicule.objects.filter(
            transporteur=self.request.user, statut=Vehicule.Statut.ACTIF, conforme=True
        )
        return form

    def form_valid(self, form):
        vehicule = form.cleaned_data["vehicule"]
        if vehicule.transporteur != self.request.user:
            messages.error(self.request, "Ce véhicule ne vous appartient pas.")
            return redirect("/flotte/vehicules/")
        if not vehicule.peut_publier_trajet():
            messages.error(
                self.request,
                f"Impossible de publier : le véhicule {vehicule.immatriculation} est "
                f"{vehicule.get_statut_display().lower()}.",
            )
            return redirect("/flotte/vehicules/")
        if form.cleaned_data["capacite_dispo_kg"] > vehicule.capacite_kg:
            form.add_error("capacite_dispo_kg", "La capacité dépasse celle du véhicule.")
            return self.form_invalid(form)
        form.instance.transporteur = self.request.user
        form.instance.capacite_totale_kg = form.cleaned_data["capacite_dispo_kg"]
        form.instance.capacite_totale_m3 = form.cleaned_data["capacite_dispo_m3"]
        messages.success(self.request, "Trajet publié.")
        return super().form_valid(form)

    def get_success_url(self):
        return "/flotte/"


class ModifierTrajetView(UpdateView):
    model = Trajet
    fields = [
        "vehicule",
        "ville_depart",
        "ville_arrivee",
        "date_depart",
        "capacite_dispo_kg",
        "capacite_dispo_m3",
        "prix_indicatif",
    ]
    template_name = "fleet/formulaire_trajet.html"

    def get_form(self, form_class=None):
        form = _styliser_formulaire(super().get_form(form_class))
        form.fields["vehicule"].queryset = Vehicule.objects.filter(
            transporteur=self.request.user,
            statut=Vehicule.Statut.ACTIF,
            conforme=True,
        )
        return form

    def get_queryset(self):
        return Trajet.objects.filter(transporteur=self.request.user)

    def form_valid(self, form):
        trajet = form.save(commit=False)
        if trajet.vehicule.transporteur_id != self.request.user.pk or not trajet.vehicule.peut_publier_trajet():
            form.add_error("vehicule", "Choisissez un véhicule actif et conforme qui vous appartient.")
            return self.form_invalid(form)
        if trajet.capacite_dispo_kg < trajet.capacite_reservee_kg:
            form.add_error("capacite_dispo_kg", "Impossible de réduire la capacité sous la part déjà réservée.")
            return self.form_invalid(form)
        if trajet.capacite_dispo_m3 < trajet.capacite_reservee_m3:
            form.add_error("capacite_dispo_m3", "Impossible de réduire le volume sous la part déjà réservée.")
            return self.form_invalid(form)
        messages.success(self.request, "Trajet modifié.")
        return super().form_valid(form)

    def get_success_url(self):
        return "/flotte/"


class AnnulerTrajetView(View):
    """Annulation (logique) d'un trajet publié."""

    def post(self, request, pk):
        trajet = get_object_or_404(Trajet, pk=pk, transporteur=request.user)
        if trajet.statut == Trajet.Statut.TERMINE:
            messages.error(request, "Un trajet terminé ne peut pas être annulé.")
        else:
            trajet.statut = Trajet.Statut.ANNULE
            trajet.save(update_fields=["statut"])
            messages.success(request, "Trajet annulé.")
        return redirect("/flotte/")


class ImpactEcologiqueView(ListeFrontView):
    """Bilan CO₂ par véhicule du transporteur connecté."""

    model = Vehicule
    roles = [Role.TRANSPORTEUR]
    titre = "Impact écologique"
    sous_titre = "Le CO₂ émis par vos trajets terminés et vos points éco."
    template_name = "fleet/impact.html"
    colonnes = []

    def get_queryset(self):
        return Vehicule.objects.filter(transporteur=self.request.user)

    def get_context_data(self, **kwargs):

        contexte = super().get_context_data(**kwargs)
        contexte["bilans"] = [
            {
                "vehicule": str(vehicule),
                "vehicule_id": vehicule.pk,
                **bilan_co2(self.request.user),
            }
            for vehicule in self.get_queryset()
        ]
        return contexte


class CertificatVertView(View):
    """Téléchargement du certificat vert PDF (année en cours par défaut)."""

    def get(self, request, pk):
        vehicule = get_object_or_404(Vehicule, pk=pk, transporteur=request.user)
        fin = timezone.localdate()
        debut = fin.replace(month=1, day=1)
        contenu, _bilan = generer_certificat_vert(vehicule.transporteur, debut, fin)
        reponse = HttpResponse(contenu, content_type="application/pdf")
        reponse["Content-Disposition"] = f'attachment; filename="certificat-vert-{vehicule.pk}.pdf"'
        return reponse


# ----------------------------------------------------------------- back-office
class BackofficeVehiculeView(ListeBackofficeView):
    model = Vehicule
    titre = "Véhicules"
    colonnes = [
        ("immatriculation", "Immatriculation"),
        ("transporteur", "Transporteur"),
        ("type", "Type"),
        ("statut", "Statut"),
        ("motif_non_conformite", "Motif"),
    ]

    def get_queryset(self):
        return Vehicule.objects.select_related("transporteur").prefetch_related("documents")


class BackofficeTrajetView(ListeBackofficeView):
    model = Trajet
    titre = "Trajets"
    colonnes = [
        ("ville_depart", "Départ"),
        ("ville_arrivee", "Arrivée"),
        ("date_depart", "Date"),
        ("transporteur", "Transporteur"),
        ("statut", "Statut"),
    ]

    def get_queryset(self):
        return Trajet.objects.select_related("vehicule", "transporteur")


class ValiderVehiculeView(View):
    """Admin : valide (ACTIF) ou refuse (NON_CONFORME) un véhicule."""

    def post(self, request, pk, decision):
        if not est_admin(request.user):
            messages.error(request, "Action réservée aux administrateurs.")
            return redirect("/backoffice/flotte/")
        vehicule = get_object_or_404(Vehicule, pk=pk)
        if decision == "valider":
            vehicule.statut = Vehicule.Statut.ACTIF
            vehicule.conforme = True
            vehicule.motif_non_conformite = ""
        else:
            vehicule.statut = Vehicule.Statut.NON_CONFORME
            vehicule.conforme = False
            vehicule.motif_non_conformite = request.POST.get("motif", "Refusé par l'administrateur")
        vehicule.save(update_fields=["statut", "conforme", "motif_non_conformite"])
        messages.success(request, f"Véhicule {vehicule.immatriculation} : {vehicule.get_statut_display()}.")
        return redirect("/backoffice/flotte/")
