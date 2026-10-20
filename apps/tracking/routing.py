from django.urls import path

from .consumers import PositionConsumer

websocket_urlpatterns = [
    path("ws/suivi/<int:reservation_id>/", PositionConsumer.as_asgi()),
]
