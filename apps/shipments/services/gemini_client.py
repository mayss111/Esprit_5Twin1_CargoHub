"""Appel Gemini. Le raisonnement interne est coupé : l'extraction n'en a pas besoin et il ralentit la réponse."""

import logging
import time

from django.conf import settings

logger = logging.getLogger(__name__)

DELAI_MS = 20_000
ESSAIS = 2
JETONS_REPONSE = 1200


def _reessayer(exc):
    code = getattr(exc, "code", None)
    if code in (408, 429, 500, 502, 503, 504):
        return True
    texte = str(exc).lower()
    return any(mot in texte for mot in ("deadline", "timeout", "timed out", "unavailable", "503", "504"))


def generer_texte(contenu):
    """Retourne le texte JSON et la durée. Relance une fois si le modèle expire."""
    from google import genai
    from google.genai import types

    client = genai.Client(
        api_key=settings.GEMINI_API_KEY,
        http_options=types.HttpOptions(timeout=DELAI_MS),
    )
    config = types.GenerateContentConfig(
        temperature=0,
        response_mime_type="application/json",
        max_output_tokens=JETONS_REPONSE,
        thinking_config=types.ThinkingConfig(thinking_level=types.ThinkingLevel.MINIMAL),
    )
    debut = time.perf_counter()
    dernier = None
    for essai in range(1, ESSAIS + 1):
        try:
            reponse = client.models.generate_content(
                model=settings.GEMINI_MODEL,
                contents=contenu,
                config=config,
            )
            duree = int((time.perf_counter() - debut) * 1000)
            return (reponse.text or ""), duree
        except Exception as exc:
            dernier = exc
            if essai == ESSAIS or not _reessayer(exc):
                break
            logger.warning("Gemini expiré (%s), second essai", type(exc).__name__)
    duree = int((time.perf_counter() - debut) * 1000)
    logger.warning("Gemini indisponible (%s) après %d ms", type(dernier).__name__, duree)
    raise dernier
