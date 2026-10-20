# Charge Celery au démarrage de Django pour que @shared_task fonctionne.
from .celery import app as celery_app

__all__ = ("celery_app",)
