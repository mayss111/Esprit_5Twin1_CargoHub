from django.contrib import admin

from .models import CodePromo, Parrainage, PointsFidelite


@admin.register(PointsFidelite)
class PointsFideliteAdmin(admin.ModelAdmin):
    pass


@admin.register(CodePromo)
class CodePromoAdmin(admin.ModelAdmin):
    pass


@admin.register(Parrainage)
class ParrainageAdmin(admin.ModelAdmin):
    pass
