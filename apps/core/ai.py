"""
Couche IA commune à toute l'équipe.

Chaque membre a sa partie IA dans le fichier `ai.py` de SON application
(ex. apps/shipments/ai.py). Tous passent par ce fichier, pour que la
configuration (clé, fournisseur, modèle) soit la même pour tout le monde.

Fournisseur : n'importe quelle API compatible OpenAI, réglée dans .env
    AI_BASE_URL=https://api.groq.com/openai/v1   (Groq, offre gratuite)
    AI_BASE_URL=http://localhost:11434/v1        (Ollama, en local)
    AI_MODEL=llama-3.3-70b-versatile

Sans AI_API_KEY, `disponible()` renvoie False : chaque fonction IA doit
alors prévoir un comportement de repli, pour que l'application marche
toujours (en local, en test, et pendant la démo si le réseau tombe).
"""

import json
import logging

from django.conf import settings

logger = logging.getLogger(__name__)


class IAIndisponible(Exception):
    """Levée quand aucune clé n'est configurée ou que le service ne répond pas."""


def disponible() -> bool:
    return bool(settings.AI_API_KEY)


def _client():
    from openai import OpenAI

    return OpenAI(api_key=settings.AI_API_KEY, base_url=settings.AI_BASE_URL, timeout=20)


def demander(
    prompt: str,
    systeme: str = "Tu es l'assistant de la plateforme CargoHub. Réponds en français.",
    temperature: float = 0.2,
) -> str:
    """Envoie une question au modèle et renvoie le texte de la réponse."""
    if not disponible():
        raise IAIndisponible("AI_API_KEY n'est pas configurée")
    try:
        reponse = _client().chat.completions.create(
            model=settings.AI_MODEL,
            temperature=temperature,
            messages=[{"role": "system", "content": systeme}, {"role": "user", "content": prompt}],
        )
        return reponse.choices[0].message.content.strip()
    except Exception as exc:  # réseau, quota, modèle inconnu…
        logger.warning("Appel IA en échec : %s", exc)
        raise IAIndisponible(str(exc)) from exc


def demander_json(prompt: str, systeme: str = "") -> dict:
    """Comme `demander`, mais exige une réponse JSON et la convertit en dict."""
    consigne = (systeme + "\n" if systeme else "") + "Réponds UNIQUEMENT avec un objet JSON valide, sans texte autour."
    texte = demander(prompt, systeme=consigne, temperature=0)
    debut, fin = texte.find("{"), texte.rfind("}")
    try:
        return json.loads(texte[debut : fin + 1])
    except ValueError as exc:
        raise IAIndisponible(f"Réponse non JSON : {texte[:200]}") from exc
