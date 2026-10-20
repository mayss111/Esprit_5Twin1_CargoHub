from django.apps import AppConfig


class PaymentsConfig(AppConfig):
    """Paiement & facturation — responsable : Membre 5."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.payments"
    label = "payments"
    verbose_name = "Paiement & facturation"
