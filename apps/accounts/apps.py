from django.apps import AppConfig


class AccountsConfig(AppConfig):
    """Comptes & sécurité — responsable : Membre 1."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.accounts"
    label = "accounts"
    verbose_name = "Comptes & sécurité"
