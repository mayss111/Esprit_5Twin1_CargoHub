"""Logique métier de la messagerie, partagée par les vues HTTP et le chat WebSocket."""

import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.urls import reverse

from apps.bookings.tasks import notifier

from .ai import moderer, moderer_par_regles
from .models import Message

logger = logging.getLogger(__name__)

TEXTE_MASQUE = "Message masqué par la modération."


class ConversationBloquee(Exception):
    pass


def envoyer_message(conversation, auteur, contenu, piece_jointe=None, fichier_audio=None, transcription=""):
    """Enregistre un message après modération. Un message signalé reste visible par son auteur et par l'admin."""
    if conversation.bloquee_par.exists():
        raise ConversationBloquee("Cette conversation est bloquée.")
    try:
        verdict = moderer(contenu)
    except Exception:  # la modération ne doit jamais empêcher d'envoyer un message
        logger.exception("Modération en échec, repli sur les règles")
        verdict = moderer_par_regles(contenu)
    message = Message.objects.create(
        conversation=conversation,
        auteur=auteur,
        contenu=contenu,
        piece_jointe=piece_jointe or "",
        fichier_audio=fichier_audio or "",
        transcription=transcription or "",
        signale=verdict["signale"],
        raison_signalement=verdict["raison"],
    )
    destinataires = conversation.participants.exclude(pk=auteur.pk).values_list("pk", flat=True)
    if message.signale:
        apercu = "Un message a été masqué par la modération."
    else:
        apercu = "Message vocal reçu." if fichier_audio else ("Pièce jointe reçue." if piece_jointe else contenu[:120])
    for destinataire_id in destinataires:
        notifier.delay(
            destinataire_id,
            "Nouveau message",
            f"{auteur} vous a envoyé un message : {apercu}",
            reverse("messaging:conversation", args=[conversation.pk]),
        )
        try:
            async_to_sync(get_channel_layer().group_send)(
                f"messagerie_notifications_{destinataire_id}",
                {
                    "type": "notification.message",
                    "titre": "Nouveau message",
                    "message": apercu,
                    "auteur": str(auteur),
                    "conversation_id": conversation.pk,
                    "lien": reverse("messaging:conversation", args=[conversation.pk]),
                },
            )
        except Exception:
            logger.warning("Notification WebSocket impossible", exc_info=True)
    return message


def texte_visible(message, lecteur):
    """Ce que `lecteur` voit du message."""
    if message.signale and message.auteur_id != lecteur.pk:
        return TEXTE_MASQUE
    return message.contenu
