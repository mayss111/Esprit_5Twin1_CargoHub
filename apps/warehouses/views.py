"""Vues du module Entrepôts & points relais — Membre 2."""

from datetime import date

from django.contrib import messages
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View
from django.views.generic import DetailView, ListView, TemplateView

from apps.core.mixins import AdminRequiredMixin, RoleRequiredMixin
from apps.core.roles import Role
from apps.shipments.forms import GOUVERNORATS
from apps.shipments.models import Expedition

from .forms import EntrepotForm
from .models import Entrepot
from .services.capacity import synthese_entrepot
from .services.distance import distance_km
from .services.reservation import STATUTS_ELIGIBLES

STATUTS_POUR_DEPOT = {
    Expedition.Statut.PUBLIEE,
    Expedition.Statut.RESERVEE,
    Expedition.Statut.LIVREE,
}


def _texte(parametre, limite=80):
    return (parametre or "").strip()[:limite]


def _entrepots_actifs(request):
    queryset = Entrepot.objects.filter(actif=True)
    nom = _texte(request.GET.get("q"))
    if nom:
        queryset = queryset.filter(Q(nom__icontains=nom) | Q(ville__icontains=nom) | Q(adresse__icontains=nom))
    ville = _texte(request.GET.get("ville"))
    if ville:
        queryset = queryset.filter(ville__icontains=ville)
    gouvernorat = _texte(request.GET.get("gouvernorat"), 40)
    connus = {valeur for valeur, _libelle in GOUVERNORATS}
    if gouvernorat in connus:
        queryset = queryset.filter(gouvernorat=gouvernorat)
    elif gouvernorat:
        queryset = queryset.none()
    return queryset


def _origine_expedition(request):
    """Coordonnées de départ si l'expédition appartient à la PME et peut être déposée."""
    brut = _texte(request.GET.get("expedition"), 12)
    if not brut:
        return None, None, ""
    if not brut.isdigit():
        return None, None, "Expédition inconnue."
    expedition = Expedition.objects.filter(pk=int(brut), pme=request.user).select_related("adresse_depart").first()
    if expedition is None:
        return None, None, "Expédition inconnue."
    if expedition.statut not in STATUTS_POUR_DEPOT:
        return None, expedition, "Cette expédition ne peut pas servir à choisir un point relais."
    depart = expedition.adresse_depart
    if depart.latitude is None or depart.longitude is None:
        return None, expedition, "L'adresse de départ n'a pas de coordonnées. La distance ne peut pas être calculée."
    return (depart.latitude, depart.longitude), expedition, ""


def _avec_distances(entrepots, origine):
    lignes = []
    for entrepot in entrepots:
        distance = None
        if origine and entrepot.latitude is not None and entrepot.longitude is not None:
            distance = distance_km(origine[0], origine[1], entrepot.latitude, entrepot.longitude)
        lignes.append({"entrepot": entrepot, "distance": distance})
    lignes.sort(key=lambda ligne: (ligne["distance"] is None, ligne["distance"] or 0, ligne["entrepot"].nom))
    return lignes


def _url_reservation(entrepot, expedition_id=""):
    url = reverse("warehouses:reserver", args=[entrepot.pk])
    if expedition_id:
        return f"{url}?expedition={expedition_id}"
    return url


def _marqueur(entrepot, url_reserver=""):
    if entrepot.latitude is None or entrepot.longitude is None:
        return None
    marqueur = {
        "nom": entrepot.nom,
        "adresse": entrepot.adresse,
        "ville": entrepot.ville,
        "gouvernorat": entrepot.gouvernorat,
        "horaires": f"{entrepot.horaire_ouverture:%H:%M} – {entrepot.horaire_fermeture:%H:%M}",
        "capacite": f"{entrepot.capacite_max_m3} m³",
        "lat": entrepot.latitude,
        "lng": entrepot.longitude,
        "url": reverse("warehouses:detail", args=[entrepot.pk]),
        "reserver": url_reserver or _url_reservation(entrepot),
    }
    stocke = entrepot.volume_present_m3()
    if stocke is not None:
        libre = entrepot.capacite_max_m3 - stocke
        marqueur["disponibilite"] = f"{libre} m³ disponibles"
    return marqueur


class PointsRelaisView(RoleRequiredMixin, TemplateView):
    """Carte et liste des entrepôts actifs. La PME ne peut pas les modifier."""

    roles = [Role.PME]
    template_name = "warehouses/liste.html"

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        origine, expedition, message = _origine_expedition(self.request)
        lignes = _avec_distances(_entrepots_actifs(self.request), origine)
        expedition_id = expedition.pk if expedition is not None and expedition.statut in STATUTS_ELIGIBLES else ""
        get = self.request.GET
        contexte.update(
            titre="Entrepôts & Points Relais",
            lignes=lignes,
            filtre={
                "q": _texte(get.get("q")),
                "ville": _texte(get.get("ville")),
                "gouvernorat": _texte(get.get("gouvernorat"), 40),
            },
            gouvernorats=GOUVERNORATS,
            expedition_id=expedition_id,
            marqueurs=[
                marqueur
                for ligne in lignes
                if (marqueur := _marqueur(ligne["entrepot"], _url_reservation(ligne["entrepot"], expedition_id)))
            ],
            expeditions=Expedition.objects.filter(pme=self.request.user, statut__in=STATUTS_POUR_DEPOT).select_related(
                "adresse_depart"
            ),
            expedition=expedition,
            origine=origine,
            avertissement=message,
            aucun_actif=not Entrepot.objects.filter(actif=True).exists(),
            recherche=any(get.get(nom) for nom in ("q", "ville", "gouvernorat", "expedition")),
        )
        return contexte


class DetailPointRelaisView(RoleRequiredMixin, DetailView):
    roles = [Role.PME]
    template_name = "warehouses/detail.html"
    context_object_name = "entrepot"

    def get_queryset(self):
        return Entrepot.objects.filter(actif=True)

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        brut = _texte(self.request.GET.get("expedition"), 12)
        expedition_id = ""
        if (
            brut.isdigit()
            and Expedition.objects.filter(pk=int(brut), pme=self.request.user, statut__in=STATUTS_ELIGIBLES).exists()
        ):
            expedition_id = brut
        marqueur = _marqueur(self.object, _url_reservation(self.object, expedition_id))
        contexte["marqueurs"] = [marqueur] if marqueur else []
        contexte["expedition_id"] = expedition_id
        contexte["occupation"] = synthese_entrepot(self.object)
        return contexte


def _filtrer_entrepots(queryset, request):
    """Filtres de la liste admin. Un paramètre inconnu ne renvoie aucun entrepôt."""
    nom = _texte(request.GET.get("q"))
    if nom:
        queryset = queryset.filter(nom__icontains=nom)
    ville = _texte(request.GET.get("ville"))
    if ville:
        queryset = queryset.filter(ville__icontains=ville)
    adresse = _texte(request.GET.get("adresse"), 120)
    if adresse:
        queryset = queryset.filter(adresse__icontains=adresse)
    gouvernorat = _texte(request.GET.get("gouvernorat"), 40)
    connus = {valeur for valeur, _libelle in GOUVERNORATS}
    if gouvernorat in connus:
        queryset = queryset.filter(gouvernorat=gouvernorat)
    elif gouvernorat:
        queryset = queryset.none()
    statut = request.GET.get("statut", "")
    if statut == "actif":
        queryset = queryset.filter(actif=True)
    elif statut == "inactif":
        queryset = queryset.filter(actif=False)
    elif statut:
        queryset = queryset.none()
    brut = _texte(request.GET.get("date"), 10)
    if brut:
        try:
            jour = date.fromisoformat(brut)
        except ValueError:
            queryset = queryset.none()
        else:
            queryset = queryset.filter(created_at__date=jour)
    return queryset


class BackofficeEntrepotView(AdminRequiredMixin, ListView):
    template_name = "warehouses/backoffice_liste.html"
    context_object_name = "entrepots"
    paginate_by = 20

    def get_queryset(self):
        return _filtrer_entrepots(Entrepot.objects.all(), self.request)

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        get = self.request.GET
        gouvernorat = _texte(get.get("gouvernorat"), 40)
        connus = {valeur for valeur, _libelle in GOUVERNORATS}
        brut = _texte(get.get("date"), 10)
        try:
            date.fromisoformat(brut)
            jour = brut
        except ValueError:
            jour = ""
        contexte.update(
            gouvernorats=GOUVERNORATS,
            recherche=any(get.get(nom) for nom in ("q", "ville", "adresse", "gouvernorat", "statut", "date")),
            filtre={
                "q": _texte(get.get("q")),
                "ville": _texte(get.get("ville")),
                "adresse": _texte(get.get("adresse"), 120),
                "gouvernorat": gouvernorat if gouvernorat in connus else "",
                "statut": get.get("statut", "") if get.get("statut") in {"actif", "inactif"} else "",
                "date": jour,
            },
        )
        return contexte


class BackofficeDetailEntrepotView(AdminRequiredMixin, DetailView):
    model = Entrepot
    template_name = "warehouses/backoffice_detail.html"
    context_object_name = "entrepot"

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        entrepot = self.object
        contexte["creneaux"] = entrepot.creneaux.select_related("expedition__pme").order_by("debut")[:20]
        contexte["occupation"] = synthese_entrepot(entrepot)
        return contexte


class BackofficeCreerEntrepotView(AdminRequiredMixin, View):
    template_name = "warehouses/backoffice_formulaire.html"

    def get(self, request):
        return render(request, self.template_name, self._contexte(EntrepotForm()))

    def post(self, request):
        formulaire = EntrepotForm(request.POST)
        if formulaire.is_valid():
            entrepot = formulaire.save()
            messages.success(request, f"L'entrepôt {entrepot.nom} est enregistré.")
            return redirect("bo_warehouses:detail", pk=entrepot.pk)
        messages.error(request, "Corrigez les champs signalés avant d'enregistrer.")
        return render(request, self.template_name, self._contexte(formulaire))

    def _contexte(self, formulaire):
        return {"formulaire": formulaire, "titre": "Ajouter un entrepôt"}


class BackofficeModifierEntrepotView(AdminRequiredMixin, View):
    template_name = "warehouses/backoffice_formulaire.html"

    def get(self, request, pk):
        entrepot = get_object_or_404(Entrepot, pk=pk)
        return render(request, self.template_name, self._contexte(EntrepotForm(instance=entrepot), entrepot))

    def post(self, request, pk):
        entrepot = get_object_or_404(Entrepot, pk=pk)
        formulaire = EntrepotForm(request.POST, instance=entrepot)
        if formulaire.is_valid():
            formulaire.save()
            messages.success(request, f"L'entrepôt {entrepot.nom} est mis à jour.")
            return redirect("bo_warehouses:detail", pk=entrepot.pk)
        messages.error(request, "Corrigez les champs signalés avant d'enregistrer.")
        return render(request, self.template_name, self._contexte(formulaire, entrepot))

    def _contexte(self, formulaire, entrepot):
        return {"formulaire": formulaire, "titre": f"Modifier {entrepot.nom}", "entrepot": entrepot}


class BackofficeDesactiverEntrepotView(AdminRequiredMixin, View):
    template_name = "warehouses/backoffice_desactiver.html"

    def get(self, request, pk):
        entrepot = get_object_or_404(Entrepot, pk=pk)
        return render(request, self.template_name, {"entrepot": entrepot})

    def post(self, request, pk):
        entrepot = get_object_or_404(Entrepot, pk=pk)
        entrepot.actif = False
        entrepot.save(update_fields=["actif", "updated_at"])
        messages.success(request, f"{entrepot.nom} est désactivé. Il reste dans l'historique.")
        return redirect("bo_warehouses:detail", pk=entrepot.pk)


class BackofficeActiverEntrepotView(AdminRequiredMixin, View):
    def post(self, request, pk):
        entrepot = get_object_or_404(Entrepot, pk=pk)
        entrepot.actif = True
        entrepot.save(update_fields=["actif", "updated_at"])
        messages.success(request, f"{entrepot.nom} accepte de nouveau les dépôts.")
        return redirect("bo_warehouses:detail", pk=entrepot.pk)
