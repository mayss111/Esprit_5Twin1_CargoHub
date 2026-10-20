"""Vues du module Fidélité & parrainage — Membre 5.

Point de départ : une page liste front-office et une page liste back-office.
Ajoutez ici vos vues de création, détail, modification…
"""

from apps.core.views import ListeBackofficeView, ListeFrontView

from .models import CodePromo


class FideliteView(ListeFrontView):
    model = CodePromo
    roles = []
    titre = "Fidélité"
    sous_titre = "Vos points, codes promo et parrainages."
    colonnes = [("code", "Code"), ("type", "Type"), ("valeur", "Valeur"), ("date_expiration", "Expire le")]

    def get_queryset(self):
        return CodePromo.objects.filter(actif=True)


class BackofficeCodePromoView(ListeBackofficeView):
    model = CodePromo
    titre = "Codes promo"
    colonnes = [("code", "Code"), ("type", "Type"), ("valeur", "Valeur"), ("actif", "Actif")]

    def get_queryset(self):
        return CodePromo.objects.all()
