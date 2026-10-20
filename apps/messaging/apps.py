from django.apps import AppConfig


class MessagingConfig(AppConfig):
    """Messagerie & support — responsable : Membre 1."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.messaging"
    label = "messaging"
    verbose_name = "Messagerie & support"
