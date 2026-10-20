from django.contrib import admin

from .models import CreneauDepot, Entrepot, MouvementColis


@admin.register(Entrepot)
class EntrepotAdmin(admin.ModelAdmin):
    pass


@admin.register(CreneauDepot)
class CreneauDepotAdmin(admin.ModelAdmin):
    pass


@admin.register(MouvementColis)
class MouvementColisAdmin(admin.ModelAdmin):
    pass
