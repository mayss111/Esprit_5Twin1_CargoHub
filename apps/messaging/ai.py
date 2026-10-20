"""
Partie IA du Membre 1 — Assistant de support et modération des messages.

1. repondre_support(question) : l'assistant répond aux questions courantes
   AVANT que l'utilisateur ouvre un ticket (moins de tickets pour l'admin).
2. moderer(texte) : détecte les messages insultants ou les tentatives de
   contourner la plateforme (numéro de téléphone, paiement en dehors…).
"""

import re

from apps.core import ai

FAQ = {
    "réserver": "Ouvrez votre expédition, cliquez sur « Trouver un camion » puis sur « Réserver ».",
    "payer": "Le paiement se fait en ligne depuis la page de la réservation, une fois acceptée.",
    "annuler": "Une réservation en attente ou acceptée peut être annulée depuis sa page.",
    "document": "Les transporteurs déposent leur permis et carte grise dans Profil > Documents.",
}

CONTEXTE = (
    "Tu es l'assistant de support de CargoHub, une plateforme tunisienne de covoiturage de fret "
    "entre PME et transporteurs. Réponds en 3 phrases maximum, en français simple. "
    "Si tu ne sais pas, conseille d'ouvrir un ticket."
)


def repondre_support(question: str) -> str:
    try:
        return ai.demander(question, systeme=CONTEXTE)
    except ai.IAIndisponible:
        q = question.lower()
        for mot, reponse in FAQ.items():
            if mot in q:
                return reponse
        return "Je n’ai pas trouvé de réponse. Ouvrez un ticket, un administrateur vous répondra."


TELEPHONE = re.compile(r"(\+216)?\s?\d{2}[\s.]?\d{3}[\s.]?\d{3}")
MOTS_INTERDITS = {"arnaque", "idiot", "imbécile"}


def moderer(texte: str) -> dict:
    """Renvoie {"signale": bool, "raison": str}."""
    try:
        return ai.demander_json(
            f"Message : « {texte} »\nCe message est-il insultant, ou essaie-t-il de faire payer "
            "ou de contacter l'autre personne en dehors de la plateforme ?",
            systeme='Format : {"signale": true|false, "raison": "..."}',
        )
    except ai.IAIndisponible:
        if TELEPHONE.search(texte):
            return {"signale": True, "raison": "Numéro de téléphone partagé"}
        if any(m in texte.lower() for m in MOTS_INTERDITS):
            return {"signale": True, "raison": "Langage inapproprié"}
        return {"signale": False, "raison": ""}
