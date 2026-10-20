from django.apps import AppConfig


class WarehousesConfig(AppConfig):
    """Entrepôts & points relais — responsable : Membre 2."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.warehouses"
    label = "warehouses"
    verbose_name = "Entrepôts & points relais"
