from django.apps import AppConfig


class TrackingConfig(AppConfig):
    """Suivi & livraison — responsable : Membre 5."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.tracking"
    label = "tracking"
    verbose_name = "Suivi & livraison"
