# Image unique utilisée en local (docker compose) ET en production (Render).
# Tout le monde a donc exactement la même version de Python et des paquets.
FROM python:3.12.8-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends libpq5 && rm -rf /var/lib/apt/lists/*

COPY requirements/ requirements/
ARG REQUIREMENTS=requirements/base.txt
RUN pip install -r ${REQUIREMENTS}

COPY . .

# Fichiers statiques compilés dans l'image (servis par WhiteNoise)
RUN DJANGO_SETTINGS_MODULE=config.settings.prod SECRET_KEY=build python manage.py collectstatic --noinput

RUN useradd --create-home cargohub && mkdir -p /app/media && chown -R cargohub /app
USER cargohub

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/sante/')"
CMD ["sh", "docker/start.sh"]
