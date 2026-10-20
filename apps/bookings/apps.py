from django.apps import AppConfig


class BookingsConfig(AppConfig):
    """Matching & réservations — responsable : Membre 4."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.bookings"
    label = "bookings"
    verbose_name = "Matching & réservations"
