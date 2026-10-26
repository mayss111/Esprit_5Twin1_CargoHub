from django.contrib import admin

from .models import Reclamation


@admin.register(Reclamation)
class ReclamationAdmin(admin.ModelAdmin):
    list_display = ("reference", "titre", "auteur", "type_reclamation", "statut", "created_at")
    list_filter = ("type_reclamation", "statut")
    search_fields = ("reference", "titre", "description", "auteur__email")
    readonly_fields = ("reference", "created_at", "updated_at", "resolue_le")
