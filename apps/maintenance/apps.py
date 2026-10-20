from django.apps import AppConfig


class MaintenanceConfig(AppConfig):
    """Entretien & conformité — responsable : Membre 3."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.maintenance"
    label = "maintenance"
    verbose_name = "Entretien & conformité"
