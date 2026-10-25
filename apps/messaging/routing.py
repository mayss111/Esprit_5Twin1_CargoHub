from django.urls import path

from .consumers import ChatConsumer, MessagerieNotificationConsumer

websocket_urlpatterns = [
    path("ws/messagerie/notifications/", MessagerieNotificationConsumer.as_asgi()),
    path("ws/messagerie/<int:conversation_id>/", ChatConsumer.as_asgi()),
]
