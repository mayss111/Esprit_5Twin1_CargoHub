from django.apps import AppConfig


class DashboardConfig(AppConfig):
    """Tableau de bord — responsable : Membre 5."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.dashboard"
    label = "dashboard"
    verbose_name = "Tableau de bord"
