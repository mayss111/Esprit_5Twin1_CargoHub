"""Tableau de bord d'occupation. Les chiffres viennent uniquement de la base."""

from django.http import JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.views import View

from apps.core.mixins import AdminRequiredMixin
from apps.warehouses.services.capacity import synthese


def contexte_occupation(request):
    nom = (request.GET.get("q") or "").strip()[:80]
    contexte = synthese(nom)
    contexte["nom"] = nom
    contexte["recherche"] = bool(nom)
    return contexte


def _json_chiffres(contexte):
    def nombre(valeur):
        if valeur is None:
            return None
        return str(valeur)

    return {
        "entrepots_actifs": contexte["entrepots_actifs"],
        "capacite": nombre(contexte["capacite"]),
        "reserve": nombre(contexte["reserve"]),
        "disponible": nombre(contexte["disponible"]),
        "taux": nombre(contexte["taux"]),
        "actives": contexte["actives"],
        "lignes": [
            {
                "id": ligne["entrepot"].pk,
                "capacite": nombre(ligne["capacite"]),
                "reserve": nombre(ligne["reserve"]),
                "disponible": nombre(ligne["disponible"]),
                "taux": nombre(ligne["taux"]),
                "barre": nombre(ligne["barre"]),
            }
            for ligne in contexte["lignes"]
        ],
    }


class BackofficeOccupationView(AdminRequiredMixin, View):
    template_name = "warehouses/backoffice_occupation.html"

    def get(self, request):
        contexte = contexte_occupation(request)
        contexte["url_chiffres"] = reverse("bo_warehouses:occupation_chiffres")
        return render(request, self.template_name, contexte)


class BackofficeOccupationChiffresView(AdminRequiredMixin, View):
    """Même calcul que la page, pour l'actualisation automatique."""

    def get(self, request):
        return JsonResponse(_json_chiffres(contexte_occupation(request)))
