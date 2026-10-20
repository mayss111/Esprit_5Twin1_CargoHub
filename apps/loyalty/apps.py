from django.apps import AppConfig


class LoyaltyConfig(AppConfig):
    """Fidélité & parrainage — responsable : Membre 5."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.loyalty"
    label = "loyalty"
    verbose_name = "Fidélité & parrainage"
