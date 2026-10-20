#!/bin/sh
# Démarrage du conteneur web : migrations, puis serveur ASGI (HTTP + WebSockets).
set -e

python manage.py migrate --noinput

# Sur l'offre gratuite de Render il n'y a pas de « background worker » :
# on lance alors Celery (worker + beat) dans le même conteneur que le site.
if [ "$RUN_CELERY_IN_WEB" = "1" ]; then
  celery -A config worker --beat --concurrency=1 --loglevel=info &
fi

exec daphne -b 0.0.0.0 -p "${PORT:-8000}" config.asgi:application
