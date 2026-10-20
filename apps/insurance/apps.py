from django.apps import AppConfig


class InsuranceConfig(AppConfig):
    """Assurance & sinistres — responsable : Membre 2."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.insurance"
    label = "insurance"
    verbose_name = "Assurance & sinistres"
