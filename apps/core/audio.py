"""Accès optionnel aux endpoints audio OpenAI, sans exposer la clé au navigateur."""

import logging

from django.conf import settings
from django.http import HttpResponse

logger = logging.getLogger(__name__)


class AudioIndisponible(Exception):
    """Le service audio n'est pas configuré ou ne répond pas."""


def _client():
    if not settings.OPENAI_API_KEY:
        raise AudioIndisponible("OPENAI_API_KEY n'est pas configurée")
    from openai import OpenAI

    return OpenAI(api_key=settings.OPENAI_API_KEY, timeout=30)


def transcrire(fichier):
    client = _client()
    try:
        with fichier.open("rb") as audio:
            resultat = client.audio.transcriptions.create(
                model=settings.OPENAI_TRANSCRIPTION_MODEL,
                file=audio,
                response_format="text",
                languages=["fr"],
            )
        return str(getattr(resultat, "text", resultat)).strip()
    except Exception as exc:
        logger.warning("Transcription audio impossible: %s", exc)
        raise AudioIndisponible(str(exc)) from exc


def synthese_vocale(texte):
    client = _client()
    try:
        resultat = client.audio.speech.create(
            model=settings.OPENAI_TTS_MODEL,
            voice=settings.OPENAI_TTS_VOICE,
            input=texte[:4096],
            response_format="mp3",
        )
        return resultat.read()
    except Exception as exc:
        logger.warning("Synthèse vocale impossible: %s", exc)
        raise AudioIndisponible(str(exc)) from exc


def tts_http_response(texte):
    contenu = synthese_vocale(texte)
    response = HttpResponse(contenu, content_type="audio/mpeg")
    response["Cache-Control"] = "private, no-store"
    return response
