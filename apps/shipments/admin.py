from django.contrib import admin

from .models import Adresse, ArticleExpedie, Expedition


class ArticleExpedieInline(admin.TabularInline):
    """Articles saisis directement sur la fiche de l'expédition."""

    model = ArticleExpedie
    extra = 1
    fields = (
        "designation",
        "description",
        "type_marchandise",
        "quantite",
        "poids_kg",
        "volume_m3",
        "fragile",
        "valeur_declaree",
    )


@admin.register(Adresse)
class AdresseAdmin(admin.ModelAdmin):
    list_display = ("ligne", "ville", "gouvernorat", "code_postal")
    search_fields = ("ligne", "ville", "gouvernorat", "code_postal")
    list_filter = ("gouvernorat",)


@admin.register(Expedition)
class ExpeditionAdmin(admin.ModelAdmin):
    list_display = (
        "reference",
        "pme",
        "ville_depart",
        "ville_arrivee",
        "date_souhaitee",
        "date_arrivee",
        "statut",
    )
    list_filter = ("statut", "date_souhaitee", "date_arrivee")
    search_fields = (
        "reference",
        "pme__email",
        "pme__first_name",
        "pme__last_name",
        "adresse_depart__ville",
        "adresse_arrivee__ville",
    )
    autocomplete_fields = ("pme", "adresse_depart", "adresse_arrivee")
    readonly_fields = ("reference", "created_at", "updated_at")
    inlines = (ArticleExpedieInline,)
    list_select_related = ("pme", "adresse_depart", "adresse_arrivee")
    date_hierarchy = "date_souhaitee"

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("articles")

    @admin.display(description="Départ", ordering="adresse_depart__ville")
    def ville_depart(self, obj):
        return obj.adresse_depart.ville

    @admin.display(description="Arrivée", ordering="adresse_arrivee__ville")
    def ville_arrivee(self, obj):
        return obj.adresse_arrivee.ville


@admin.register(ArticleExpedie)
class ArticleExpedieAdmin(admin.ModelAdmin):
    list_display = ("designation", "expedition", "type_marchandise", "quantite", "poids_kg", "fragile")
    list_filter = ("type_marchandise", "fragile")
    search_fields = ("designation", "expedition__reference", "expedition__pme__email")
    autocomplete_fields = ("expedition",)
    list_select_related = ("expedition",)
