from django.apps import AppConfig


class FleetConfig(AppConfig):
    """Flotte & trajets — responsable : Membre 3."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.fleet"
    label = "fleet"
    verbose_name = "Flotte & trajets"
