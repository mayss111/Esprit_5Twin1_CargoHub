from django.apps import AppConfig


class ShipmentsConfig(AppConfig):
    """Expéditions — responsable : Membre 2."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.shipments"
    label = "shipments"
    verbose_name = "Expéditions"
