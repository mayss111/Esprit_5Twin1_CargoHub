from django.contrib import admin

from .models import Adresse, ArticleExpedie, Expedition


@admin.register(Adresse)
class AdresseAdmin(admin.ModelAdmin):
    pass


@admin.register(Expedition)
class ExpeditionAdmin(admin.ModelAdmin):
    pass


@admin.register(ArticleExpedie)
class ArticleExpedieAdmin(admin.ModelAdmin):
    pass
