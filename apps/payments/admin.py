from django.contrib import admin

from .models import Commission, Facture, Paiement


@admin.register(Paiement)
class PaiementAdmin(admin.ModelAdmin):
    pass


@admin.register(Facture)
class FactureAdmin(admin.ModelAdmin):
    pass


@admin.register(Commission)
class CommissionAdmin(admin.ModelAdmin):
    pass
