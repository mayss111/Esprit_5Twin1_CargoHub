from django.contrib import admin

from .models import PieceJustificative, PoliceAssurance, Sinistre


@admin.register(PoliceAssurance)
class PoliceAssuranceAdmin(admin.ModelAdmin):
    pass


@admin.register(Sinistre)
class SinistreAdmin(admin.ModelAdmin):
    pass


@admin.register(PieceJustificative)
class PieceJustificativeAdmin(admin.ModelAdmin):
    pass
