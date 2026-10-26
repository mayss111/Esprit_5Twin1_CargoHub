from django.contrib import admin

from .models import PieceJustificative, PoliceAssurance, Sinistre


@admin.register(PoliceAssurance)
class PoliceAssuranceAdmin(admin.ModelAdmin):
    pass


@admin.register(Sinistre)
class SinistreAdmin(admin.ModelAdmin):
    list_display = ("reference", "titre", "auteur", "type_sinistre", "statut", "date_incident")
    list_filter = ("type_sinistre", "statut")
    search_fields = ("reference", "titre", "description", "auteur__email")
    readonly_fields = ("reference", "created_at", "updated_at", "resolu_le")


@admin.register(PieceJustificative)
class PieceJustificativeAdmin(admin.ModelAdmin):
    pass
