from django.contrib import admin

from .models import ControleTechnique, DepenseVehicule, Entretien


@admin.register(Entretien)
class EntretienAdmin(admin.ModelAdmin):
    pass


@admin.register(ControleTechnique)
class ControleTechniqueAdmin(admin.ModelAdmin):
    pass


@admin.register(DepenseVehicule)
class DepenseVehiculeAdmin(admin.ModelAdmin):
    pass
