"""Scan administrateur des entrées et sorties. Le QR Code ne modifie rien tout seul."""

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import View
from django.views.generic import ListView

from apps.core.mixins import AdminRequiredMixin
from apps.warehouses.models import Entrepot, MouvementColis
from apps.warehouses.services.reservation import parse_date
from apps.warehouses.services.scan import (
    analyser,
    confirmer_entree,
    confirmer_sortie,
    etat_stockage,
    nombre_alertes,
    prolonger,
)


class ScannerView(AdminRequiredMixin, View):
    template_name = "warehouses/backoffice_scanner.html"

    def get(self, request):
        return render(request, self.template_name, {"apercu": None, "jeton": ""})

    def post(self, request):
        jeton = request.POST.get("jeton", "")
        if "confirmer_entree" in request.POST:
            mouvement, erreur = confirmer_entree(
                jeton,
                request.user,
                exceptionnel=request.POST.get("exceptionnel") == "on",
                motif=request.POST.get("motif", ""),
            )
            if erreur:
                messages.error(request, erreur)
            else:
                messages.success(request, f"Entrée enregistrée pour {mouvement.expedition.reference}.")
                return redirect("bo_warehouses:mouvements")
        elif "confirmer_sortie" in request.POST:
            mouvement, erreur = confirmer_sortie(jeton, request.user, request.POST.get("commentaire", ""))
            if erreur:
                messages.error(request, erreur)
            else:
                messages.success(request, f"Sortie enregistrée pour {mouvement.expedition.reference}.")
                return redirect("bo_warehouses:mouvements")
        apercu = analyser(jeton) if str(jeton).strip() else None
        if apercu is None:
            messages.error(request, "Scannez ou collez un QR Code.")
        return render(request, self.template_name, {"apercu": apercu, "jeton": jeton})


class MouvementsView(AdminRequiredMixin, ListView):
    template_name = "warehouses/backoffice_mouvements.html"
    context_object_name = "mouvements"
    paginate_by = 20

    def get_queryset(self):
        queryset = MouvementColis.objects.select_related(
            "entrepot", "expedition", "expedition__pme", "scanne_par", "creneau"
        )
        recherche = (self.request.GET.get("q") or "").strip()[:40]
        if recherche:
            queryset = queryset.filter(expedition__reference__icontains=recherche)
        type_mouvement = (self.request.GET.get("type") or "").strip()
        if type_mouvement in MouvementColis.Type.values:
            queryset = queryset.filter(type=type_mouvement)
        elif type_mouvement:
            queryset = queryset.none()
        entrepot = (self.request.GET.get("entrepot") or "").strip()
        if entrepot.isdigit():
            queryset = queryset.filter(entrepot_id=int(entrepot))
        elif entrepot:
            queryset = queryset.none()
        jour, erreur = parse_date(self.request.GET.get("date"))
        if self.request.GET.get("date") and erreur:
            queryset = queryset.none()
        elif jour is not None:
            queryset = queryset.filter(date__date=jour)
        if self.request.GET.get("presents") == "1" or self.request.GET.get("retard") == "1":
            queryset = queryset.filter(type=MouvementColis.Type.ENTREE, ouvert=True)
        self.filtre = {
            "q": recherche,
            "type": type_mouvement if type_mouvement in MouvementColis.Type.values else "",
            "entrepot": entrepot if entrepot.isdigit() else "",
            "date": jour.isoformat() if jour else "",
            "presents": self.request.GET.get("presents") == "1",
            "retard": self.request.GET.get("retard") == "1",
        }
        if self.filtre["retard"]:
            maintenant = timezone.now()
            identifiants = [
                entree.pk
                for entree in queryset.select_related("entrepot")
                if (etat := etat_stockage(entree, maintenant)) and (etat["depasse"] or etat["approche"])
            ]
            queryset = queryset.filter(pk__in=identifiants)
        return queryset

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        maintenant = timezone.now()
        contexte["lignes"] = [
            {
                "mouvement": mouvement,
                "stockage": etat_stockage(mouvement, maintenant) if mouvement.ouvert else None,
            }
            for mouvement in contexte["mouvements"]
        ]
        contexte["filtre"] = self.filtre
        contexte["entrepots"] = Entrepot.objects.order_by("nom")
        contexte["types"] = MouvementColis.Type.choices
        contexte["retards"] = nombre_alertes(maintenant)
        return contexte


class ProlongerStockageView(AdminRequiredMixin, View):
    def post(self, request, pk):
        get_object_or_404(MouvementColis, pk=pk, type=MouvementColis.Type.ENTREE)
        entree, erreur = prolonger(pk, request.POST.get("heures"), request.POST.get("motif"))
        if erreur:
            messages.error(request, erreur)
        else:
            messages.success(
                request,
                f"Stockage prolongé de {entree.prolongation_heures} h pour {entree.expedition.reference}.",
            )
        return redirect("bo_warehouses:mouvements")
