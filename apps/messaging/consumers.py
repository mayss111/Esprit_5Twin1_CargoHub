"""Chat en temps réel — Membre 1. Côté navigateur : new WebSocket("/ws/messagerie/<id>/")."""

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from .models import Conversation, Message


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
        texte = (content.get("message") or "").strip()
        if not texte:
            return
        await self._enregistrer(texte)
        await self.channel_layer.group_send(
            self.groupe, {"type": "chat.message", "message": texte, "auteur": str(self.scope["user"])}
        )

    async def chat_message(self, event):
        await self.send_json({"message": event["message"], "auteur": event["auteur"]})

    @database_sync_to_async
    def _participe(self, user):
        return Conversation.objects.filter(pk=self.conversation_id, participants=user).exists()

    @database_sync_to_async
    def _enregistrer(self, texte):
        Message.objects.create(conversation_id=self.conversation_id, auteur=self.scope["user"], contenu=texte)
