"""Configuration de production (Render)."""

from .base import *  # noqa: F401,F403
from .base import env

DEBUG = False

# Render fournit le nom d'hôte du service dans cette variable.
RENDER_HOST = env("RENDER_EXTERNAL_HOSTNAME", default="")
if RENDER_HOST:
    ALLOWED_HOSTS.append(RENDER_HOST)  # noqa: F405
    CSRF_TRUSTED_ORIGINS.append(f"https://{RENDER_HOST}")  # noqa: F405

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=True)
SECURE_REDIRECT_EXEMPT = [r"^sante/$"]  # le test de santé de Render arrive en HTTP
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 60 * 60 * 24
SECURE_CONTENT_TYPE_NOSNIFF = True
