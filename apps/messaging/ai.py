"""
Partie IA du Membre 1 — Assistant de support et modération des messages.

1. repondre_support(question) : l'assistant répond aux questions courantes
   AVANT que l'utilisateur ouvre un ticket (moins de tickets pour l'admin).
2. moderer(texte) : détecte les messages insultants ou les tentatives de
   contourner la plateforme (numéro de téléphone, paiement en dehors…).

Sans clé d'IA (tests, démo hors ligne), les deux fonctions utilisent des règles simples.
"""

import re

from apps.core import ai

FAQ = {
    "réserver": "Ouvrez votre expédition, cliquez sur « Trouver un camion » puis sur « Réserver ».",
    "payer": "Le paiement se fait en ligne depuis la page de la réservation, une fois acceptée.",
    "paiement": "Le paiement se fait en ligne depuis la page de la réservation, une fois acceptée.",
    "annuler": "Une réservation en attente ou acceptée peut être annulée depuis sa page.",
    "document": "Les transporteurs déposent leur permis et carte grise dans Profil > Modifier mon profil.",
    "contrat": "Le contrat se génère dans « Mes contrats » une fois la réservation acceptée, puis se signe en ligne.",
    "mot de passe": "Sur la page de connexion, cliquez sur « Mot de passe oublié ? » pour recevoir un lien par email.",
    "suivi": "La position du camion s’affiche en direct dans « Suivi » pendant le transport.",
    "assurance": "Vous pouvez assurer une expédition et déclarer un sinistre depuis le menu « Assurance ».",
}

CONTEXTE = (
    "Tu es l'assistant de support de CargoHub, une plateforme tunisienne de covoiturage de fret "
    "entre PME et transporteurs. Fonctions disponibles : publier une expédition, réserver un trajet, "
    "payer en ligne après acceptation, signer le contrat dans « Mes contrats », suivre le camion en direct, "
    "assurer un envoi, messagerie avec l'autre partie. Le paiement et les échanges se font UNIQUEMENT "
    "sur la plateforme. Réponds en 3 phrases maximum, en français simple. "
    "Si la question concerne un cas particulier (litige, remboursement, bug) ou si tu ne sais pas, "
    "conseille d'ouvrir un ticket de support."
)

REPONSE_PAR_DEFAUT = "Je n’ai pas trouvé de réponse. Ouvrez un ticket, un administrateur vous répondra."


def repondre_support(question: str) -> str:
    try:
        return ai.demander(question, systeme=CONTEXTE)
    except ai.IAIndisponible:
        q = question.lower()
        for mot, reponse in FAQ.items():
            if mot in q:
                return reponse
        return REPONSE_PAR_DEFAUT


# ---------------------------------------------------------------- modération

TELEPHONE = re.compile(r"(\+216)?\s?\d{2}[\s.]?\d{3}[\s.]?\d{3}")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
MOTS_INTERDITS = {"arnaque", "idiot", "imbécile", "escroc", "voleur", "minable", "crétin", "abruti"}
CONTOURNEMENT = re.compile(
    r"hors (de la )?plate-?forme|sans passer par|(règl|régl|pay|trait)\w* (ça |tout )?en direct|"
    r"en espèces|en liquide|\bcash\b|de la main à la main|whats ?app|viber|messenger|"
    r"éviter (la|les) (commission|frais)",
    re.IGNORECASE,
)

CONSIGNE_MODERATION = (
    "Tu modères la messagerie d'une plateforme de transport de marchandises. Un message doit être signalé "
    "s'il contient une insulte ou une menace, OU s'il cherche à continuer l'échange ou le paiement en dehors "
    "de la plateforme (numéro de téléphone, email, réseau social, paiement en espèces, éviter la commission). "
    "Les questions pratiques sur une livraison (horaire, adresse, poids, retard) sont normales.\n"
    'Format : {"signale": true|false, "raison": "explication courte en français, vide si non signalé"}'
)


def moderer_par_regles(texte: str) -> dict:
    """Repli sans IA : expressions régulières et liste de mots."""
    if TELEPHONE.search(texte):
        return {"signale": True, "raison": "Numéro de téléphone partagé"}
    if EMAIL.search(texte):
        return {"signale": True, "raison": "Adresse email partagée"}
    if CONTOURNEMENT.search(texte):
        return {"signale": True, "raison": "Tentative de contourner la plateforme"}
    mots = set(re.findall(r"[\wéèêàùç]+", texte.lower()))
    if mots & MOTS_INTERDITS:
        return {"signale": True, "raison": "Langage inapproprié"}
    return {"signale": False, "raison": ""}


def moderer(texte: str) -> dict:
    """Renvoie {"signale": bool, "raison": str}."""
    try:
        reponse = ai.demander_json(f"Message : « {texte} »", systeme=CONSIGNE_MODERATION)
    except ai.IAIndisponible:
        return moderer_par_regles(texte)
    signale = reponse.get("signale") in (True, "true", "True", 1)
    return {"signale": signale, "raison": str(reponse.get("raison") or "")[:200] if signale else ""}
