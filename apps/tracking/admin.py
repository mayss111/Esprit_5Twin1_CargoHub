from django.contrib import admin

from .models import Avis, Incident, PreuveLivraison, SuiviPosition


@admin.register(SuiviPosition)
class SuiviPositionAdmin(admin.ModelAdmin):
    pass


@admin.register(PreuveLivraison)
class PreuveLivraisonAdmin(admin.ModelAdmin):
    pass


@admin.register(Incident)
class IncidentAdmin(admin.ModelAdmin):
    pass


@admin.register(Avis)
class AvisAdmin(admin.ModelAdmin):
    pass
