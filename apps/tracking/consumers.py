"""Suivi du camion en temps réel — Membre 5. Côté navigateur : new WebSocket("/ws/suivi/<id>/").

Le transporteur envoie {"lat": .., "lng": ..} ; la PME reçoit chaque nouvelle position.
"""

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.db.models import Q

from apps.bookings.models import Reservation

from .models import SuiviPosition


class PositionConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        self.reservation_id = int(self.scope["url_route"]["kwargs"]["reservation_id"])
        self.groupe = f"suivi_{self.reservation_id}"
        user = self.scope["user"]
        self.est_transporteur = False
        if not user.is_authenticated or not await self._autorise(user):
            await self.close()
            return
        await self.channel_layer.group_add(self.groupe, self.channel_name)
        await self.accept()

    async def disconnect(self, code):
        await self.channel_layer.group_discard(self.groupe, self.channel_name)

    async def receive_json(self, content, **kwargs):
        if not self.est_transporteur:
            return  # seul le transporteur envoie sa position
        lat, lng = float(content["lat"]), float(content["lng"])
        await self._enregistrer(lat, lng)
        await self.channel_layer.group_send(self.groupe, {"type": "position", "lat": lat, "lng": lng})

    async def position(self, event):
        await self.send_json({"lat": event["lat"], "lng": event["lng"]})

    @database_sync_to_async
    def _autorise(self, user):
        reservation = (
            Reservation.objects.filter(Q(expedition__pme=user) | Q(trajet__transporteur=user), pk=self.reservation_id)
            .select_related("trajet")
            .first()
        )
        if reservation:
            self.est_transporteur = reservation.trajet.transporteur_id == user.id
        return reservation is not None

    @database_sync_to_async
    def _enregistrer(self, lat, lng):
        SuiviPosition.objects.create(reservation_id=self.reservation_id, latitude=lat, longitude=lng)
