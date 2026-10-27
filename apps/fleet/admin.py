from django.contrib import admin

from .models import DocumentVehicule, EtapeTrajet, FacteurEmission, Trajet, Vehicule


class DocumentVehiculeInline(admin.TabularInline):
    model = DocumentVehicule
    extra = 0


@admin.register(Vehicule)
class VehiculeAdmin(admin.ModelAdmin):
    list_display = ["immatriculation", "type", "transporteur", "statut", "conforme", "motif_non_conformite"]
    list_filter = ["statut", "type", "conforme"]
    search_fields = ["immatriculation"]
    inlines = [DocumentVehiculeInline]


@admin.register(Trajet)
class TrajetAdmin(admin.ModelAdmin):
    list_display = ["ville_depart", "ville_arrivee", "date_depart", "vehicule", "statut", "capacite_dispo_kg", "co2_kg"]
    list_filter = ["statut"]


@admin.register(EtapeTrajet)
class EtapeTrajetAdmin(admin.ModelAdmin):
    pass


@admin.register(FacteurEmission)
class FacteurEmissionAdmin(admin.ModelAdmin):
    list_display = ["type_vehicule", "kg_co2_par_km"]
