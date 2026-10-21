"""Logique métier de la messagerie, partagée par les vues HTTP et le chat WebSocket."""

import logging

from .ai import moderer, moderer_par_regles
from .models import Message

logger = logging.getLogger(__name__)

TEXTE_MASQUE = "Message masqué par la modération."


def envoyer_message(conversation, auteur, contenu, piece_jointe=None):
    """Enregistre un message après modération. Un message signalé reste visible par son auteur et par l'admin."""
    try:
        verdict = moderer(contenu)
    except Exception:  # la modération ne doit jamais empêcher d'envoyer un message
        logger.exception("Modération en échec, repli sur les règles")
        verdict = moderer_par_regles(contenu)
    return Message.objects.create(
        conversation=conversation,
        auteur=auteur,
        contenu=contenu,
        piece_jointe=piece_jointe or "",
        signale=verdict["signale"],
        raison_signalement=verdict["raison"],
    )


def texte_visible(message, lecteur):
    """Ce que `lecteur` voit du message."""
    if message.signale and message.auteur_id != lecteur.pk:
        return TEXTE_MASQUE
    return message.contenu
