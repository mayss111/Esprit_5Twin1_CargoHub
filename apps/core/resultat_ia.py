"""Résultat d'une tâche IA partagé entre le site et le worker Celery.

Sans Redis, le cache du process suffit : la tâche tourne dans la requête.
Avec Redis, le worker et le site ne partagent pas la mémoire, le résultat passe par Redis.
"""

import json

from django.conf import settings
from django.core.cache import cache

DUREE = 600


def _via_redis():
    return bool(settings.REDIS_URL) and not settings.CELERY_TASK_ALWAYS_EAGER


def ecrire(cle, valeur, duree=DUREE):
    if not _via_redis():
        cache.set(cle, valeur, duree)
        return
    from redis import Redis

    Redis.from_url(settings.REDIS_URL).set(cle, json.dumps(valeur), ex=duree)


def lire(cle):
    if not _via_redis():
        return cache.get(cle)
    from redis import Redis

    brut = Redis.from_url(settings.REDIS_URL).get(cle)
    if brut is None:
        return None
    return json.loads(brut)
