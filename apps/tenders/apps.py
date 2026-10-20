from django.apps import AppConfig


class TendersConfig(AppConfig):
    """Appels d’offres & négociation — responsable : Membre 4."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.tenders"
    label = "tenders"
    verbose_name = "Appels d’offres & négociation"
