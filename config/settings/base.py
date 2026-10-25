"""
Configuration commune à tous les environnements (dev, test, prod).

Ne mettez JAMAIS de secret ici : tout ce qui change d'un poste à l'autre
se lit dans le fichier .env (voir .env.example).
"""

from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("SECRET_KEY", default="dev-insecure-change-me")
DEBUG = env.bool("DEBUG", default=False)
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])

# ---------------------------------------------------------------- applications
DJANGO_APPS = [
    "daphne",  # serveur ASGI (HTTP + WebSockets) — doit rester en premier
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "whitenoise.runserver_nostatic",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
]
THIRD_PARTY_APPS = [
    "channels",
    "crispy_forms",
    "crispy_bootstrap5",
]
# Une application = un module. Le commentaire indique le membre responsable.
LOCAL_APPS = [
    "apps.core",  # partagé : base, rôles, couche IA
    "apps.accounts",  # M1 — Comptes & sécurité
    "apps.messaging",  # M1 — Messagerie & support
    "apps.contracts",  # M1 — Contrats & documents
    "apps.shipments",  # M2 — Expéditions
    "apps.warehouses",  # M2 — Entrepôts & points relais
    "apps.insurance",  # M2 — Assurance & sinistres
    "apps.fleet",  # M3 — Flotte & trajets
    "apps.maintenance",  # M3 — Entretien & conformité
    "apps.ecology",  # M3 — Impact écologique
    "apps.bookings",  # M4 — Matching & réservations
    "apps.tenders",  # M4 — Appels d'offres & négociation
    "apps.tracking",  # M5 — Suivi & livraison
    "apps.payments",  # M5 — Paiement & facturation
    "apps.loyalty",  # M5 — Fidélité & parrainage
    "apps.dashboard",  # M5 — Tableau de bord global (back-office)
]
INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.core.context_processors.navigation",
            ],
        },
    },
]

# ---------------------------------------------------------------- base de données
# PostgreSQL via DATABASE_URL (Docker). Sans .env : SQLite, pratique pour un test rapide.
DATABASES = {
    "default": env.db("DATABASE_URL", default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}"),
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------- authentification
AUTH_USER_MODEL = "accounts.Utilisateur"
LOGIN_URL = "accounts:connexion"
LOGIN_REDIRECT_URL = "core:accueil"
LOGOUT_REDIRECT_URL = "core:accueil"
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ---------------------------------------------------------------- langue et fuseau
LANGUAGE_CODE = "fr"
# Une seule langue : même si le navigateur est en anglais, les messages restent en français.
LANGUAGES = [("fr", "Français")]
TIME_ZONE = "Africa/Tunis"
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------- fichiers
STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

CRISPY_ALLOWED_TEMPLATE_PACKS = "bootstrap5"
CRISPY_TEMPLATE_PACK = "bootstrap5"

# ---------------------------------------------------------------- Redis, Celery, Channels
REDIS_URL = env("REDIS_URL", default="")

CELERY_BROKER_URL = REDIS_URL or "memory://"
CELERY_RESULT_BACKEND = None
CELERY_TIMEZONE = TIME_ZONE
# Sans Redis, les tâches s'exécutent tout de suite (pratique en local et en test).
CELERY_TASK_ALWAYS_EAGER = env.bool("CELERY_TASK_ALWAYS_EAGER", default=not REDIS_URL)
CELERY_BEAT_SCHEDULE = {
    # M3 — recrée chaque jour les trajets récurrents de la semaine suivante
    "trajets-recurrents": {"task": "apps.fleet.tasks.generer_trajets_recurrents", "schedule": 60 * 60 * 24},
    # M3 — rappels d'entretien et blocage des véhicules non conformes
    "verifier-conformite": {"task": "apps.maintenance.tasks.verifier_conformite", "schedule": 60 * 60 * 24},
    # M4 — clôture automatique des appels d'offres
    "cloturer-appels-offres": {"task": "apps.tenders.tasks.cloturer_appels_offres", "schedule": 60 * 5},
}

CHANNEL_LAYERS = {
    "default": (
        {"BACKEND": "channels_redis.core.RedisChannelLayer", "CONFIG": {"hosts": [REDIS_URL]}}
        if REDIS_URL
        else {"BACKEND": "channels.layers.InMemoryChannelLayer"}
    )
}

# ---------------------------------------------------------------- emails
EMAIL_BACKEND = env("EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend")
EMAIL_HOST = env("EMAIL_HOST", default="")
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = True
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="CargoHub <no-reply@cargohub.tn>")

# ---------------------------------------------------------------- services externes
# IA : n'importe quel fournisseur compatible avec l'API OpenAI (Groq, OpenRouter, Ollama…)
AI_API_KEY = env("AI_API_KEY", default="")
AI_BASE_URL = env("AI_BASE_URL", default="https://api.groq.com/openai/v1")
AI_MODEL = env("AI_MODEL", default="llama-3.3-70b-versatile")

STRIPE_SECRET_KEY = env("STRIPE_SECRET_KEY", default="")
STRIPE_PUBLIC_KEY = env("STRIPE_PUBLIC_KEY", default="")
STRIPE_WEBHOOK_SECRET = env("STRIPE_WEBHOOK_SECRET", default="")

OSRM_URL = env("OSRM_URL", default="https://router.project-osrm.org")

# Taux de commission de la plateforme (modifiable par l'admin plus tard — M5)
COMMISSION_TAUX = env.float("COMMISSION_TAUX", default=0.10)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO"},
}
