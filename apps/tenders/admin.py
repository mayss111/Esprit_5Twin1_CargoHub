from django.contrib import admin

from .models import AppelOffre, ContreProposition, Offre


@admin.register(AppelOffre)
class AppelOffreAdmin(admin.ModelAdmin):
    pass


@admin.register(Offre)
class OffreAdmin(admin.ModelAdmin):
    pass


@admin.register(ContreProposition)
class ContrePropositionAdmin(admin.ModelAdmin):
    pass
