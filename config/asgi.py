"""
Point d'entrée ASGI : sert les pages HTTP et les WebSockets
(chat en temps réel — M1, suivi du camion en temps réel — M5).
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
django_asgi_app = get_asgi_application()

from channels.auth import AuthMiddlewareStack  # noqa: E402
from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402
from channels.security.websocket import AllowedHostsOriginValidator  # noqa: E402

from apps.messaging.routing import websocket_urlpatterns as messaging_ws  # noqa: E402
from apps.tracking.routing import websocket_urlpatterns as tracking_ws  # noqa: E402

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": AllowedHostsOriginValidator(
            AuthMiddlewareStack(URLRouter(messaging_ws + tracking_ws))
        ),
    }
)
