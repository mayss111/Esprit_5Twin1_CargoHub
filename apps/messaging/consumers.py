"""Chat en temps réel — Membre 1. Côté navigateur : new WebSocket("/ws/messagerie/<id>/")."""

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.utils import timezone

from apps.core.roles import est_admin

from .models import Conversation
from .services import TEXTE_MASQUE, ConversationBloquee, envoyer_message


class ChatConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        self.conversation_id = int(self.scope["url_route"]["kwargs"]["conversation_id"])
        self.groupe = f"conversation_{self.conversation_id}"
        user = self.scope["user"]
        if not user.is_authenticated or not await self._participe(user):
            await self.close()
            return
        await self.channel_layer.group_add(self.groupe, self.channel_name)
        await self.accept()

    async def disconnect(self, code):
        await self.channel_layer.group_discard(self.groupe, self.channel_name)

    async def receive_json(self, content, **kwargs):
        texte = (content.get("message") or "").strip()[:2000]
        if not texte:
            return
        message = await self._enregistrer(texte)
        if message is None:
            await self.send_json({"error": "Cette conversation est bloquée."})
            return
        await self.channel_layer.group_send(
            self.groupe,
            {
                "type": "chat.message",
                "message": TEXTE_MASQUE if message.signale else texte,
                "auteur": str(self.scope["user"]),
                "auteur_id": self.scope["user"].pk,
                "date": timezone.localtime(message.created_at).strftime("%d/%m %H:%M"),
            },
        )

    async def chat_message(self, event):
        await self.send_json({k: v for k, v in event.items() if k != "type"})

    @database_sync_to_async
    def _participe(self, user):
        return est_admin(user) or Conversation.objects.filter(pk=self.conversation_id, participants=user).exists()

    @database_sync_to_async
    def _enregistrer(self, texte):
        conversation = Conversation.objects.get(pk=self.conversation_id)
        try:
            return envoyer_message(conversation, self.scope["user"], texte)
        except ConversationBloquee:
            return None


class MessagerieNotificationConsumer(AsyncJsonWebsocketConsumer):
    """Canal privé pour actualiser la cloche de messagerie sans rechargement."""

    async def connect(self):
        user = self.scope["user"]
        if not user.is_authenticated:
            await self.close()
            return
        self.groupe = f"messagerie_notifications_{user.pk}"
        await self.channel_layer.group_add(self.groupe, self.channel_name)
        await self.accept()

    async def disconnect(self, code):
        if hasattr(self, "groupe"):
            await self.channel_layer.group_discard(self.groupe, self.channel_name)

    async def notification_message(self, event):
        await self.send_json({k: v for k, v in event.items() if k != "type"})
