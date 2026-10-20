from django.contrib import admin

from .models import EtapeTrajet, Trajet, Vehicule


@admin.register(Vehicule)
class VehiculeAdmin(admin.ModelAdmin):
    pass


@admin.register(Trajet)
class TrajetAdmin(admin.ModelAdmin):
    pass


@admin.register(EtapeTrajet)
class EtapeTrajetAdmin(admin.ModelAdmin):
    pass
