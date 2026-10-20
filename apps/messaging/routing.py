from django.urls import path

from .consumers import ChatConsumer

websocket_urlpatterns = [
    path("ws/messagerie/<int:conversation_id>/", ChatConsumer.as_asgi()),
]
