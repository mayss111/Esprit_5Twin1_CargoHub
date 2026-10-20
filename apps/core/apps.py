from django.apps import AppConfig


class CoreConfig(AppConfig):
    """Socle commun — responsable : toute l’équipe."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.core"
    label = "core"
    verbose_name = "Socle commun"
