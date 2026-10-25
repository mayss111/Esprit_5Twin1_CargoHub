import logging
import os
import sys

from django.apps import AppConfig

logger = logging.getLogger(__name__)

# Commandes qui n'utilisent pas l'IA : inutile de charger scikit-learn (et le build Docker reste rapide).
COMMANDES_SANS_IA = {"migrate", "makemigrations", "collectstatic", "showmigrations", "sqlmigrate", "test", "check"}


def doit_prechauffer(argv=None, en_test=None) -> bool:
    """Vrai pour le site (daphne, runserver) et le worker Celery ; faux pendant les tests et les migrations."""
    argv = sys.argv if argv is None else argv
    if en_test is None:
        en_test = "pytest" in sys.modules or os.environ.get("DJANGO_SETTINGS_MODULE", "").endswith(".test")
    if en_test:
        return False
    commande = argv[1] if len(argv) > 1 and argv[0].endswith("manage.py") else ""
    return commande not in COMMANDES_SANS_IA


class TendersConfig(AppConfig):
    """Appels d’offres & négociation — responsable : Membre 4."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.tenders"
    label = "tenders"
    verbose_name = "Appels d’offres & négociation"

    def ready(self):
        """Précharge scikit-learn au démarrage (site ET worker Celery) : le 1er « Suggérer un prix » ne paie plus
        les ~10 s d'import. Ne doit jamais empêcher l'application de démarrer."""
        if not doit_prechauffer():
            return
        try:
            from .ai import chauffer_modele

            chauffer_modele()
        except Exception:
            logger.warning(
                "Préchargement de scikit-learn impossible (l'IA se chargera au premier appel)", exc_info=True
            )
