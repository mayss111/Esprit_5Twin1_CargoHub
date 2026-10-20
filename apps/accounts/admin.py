from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import ProfilPME, ProfilTransporteur, Utilisateur


@admin.register(Utilisateur)
class UtilisateurAdmin(UserAdmin):
    ordering = ["email"]
    list_display = ["email", "first_name", "last_name", "role", "is_active"]
    list_filter = ["role", "is_active"]
    search_fields = ["email", "first_name", "last_name"]
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Identité", {"fields": ("first_name", "last_name", "telephone", "role")}),
        ("Droits", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
    )
    add_fieldsets = ((None, {"classes": ("wide",), "fields": ("email", "role", "password1", "password2")}),)


@admin.register(ProfilPME)
class ProfilPMEAdmin(admin.ModelAdmin):
    list_display = ["raison_sociale", "ville", "utilisateur"]


@admin.register(ProfilTransporteur)
class ProfilTransporteurAdmin(admin.ModelAdmin):
    list_display = ["utilisateur", "statut_validation", "note_moyenne"]
    list_filter = ["statut_validation"]
