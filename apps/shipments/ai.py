"""
Partie IA du Membre 2 — Saisie intelligente d'une expédition.

La PME décrit son envoi en une phrase (« 12 cartons de vêtements, environ
300 kg, de Monastir à Tunis ») et l'IA pré-remplit le formulaire :
articles, type de marchandise, poids, et alerte si la marchandise est interdite.
"""

import re

from apps.core import ai

from .models import ArticleExpedie

MOTS_TYPES = {
    ArticleExpedie.Type.ALIMENTAIRE: ["huile", "dattes", "fromage", "légume", "fruit", "farine", "conserve"],
    ArticleExpedie.Type.TEXTILE: ["vêtement", "tissu", "textile", "chaussure"],
    ArticleExpedie.Type.ELECTRONIQUE: ["ordinateur", "téléphone", "écran", "électronique"],
    ArticleExpedie.Type.MATERIAUX: ["ciment", "carrelage", "brique", "bois", "fer"],
    ArticleExpedie.Type.INTERDIT: ["arme", "explosif", "drogue", "gaz inflammable"],
}


def analyser_description(texte: str) -> dict:
    """
    Renvoie {"designation", "type_marchandise", "quantite", "poids_kg", "interdit"}.
    """
    try:
        data = ai.demander_json(
            f"Description d'un envoi : « {texte} ».\nExtrais : designation (courte), type_marchandise parmi "
            f"{[t.value for t in ArticleExpedie.Type]}, quantite (entier), poids_kg (nombre ou null), "
            "interdit (true si la marchandise est dangereuse ou illégale)."
        )
        if data.get("type_marchandise") not in ArticleExpedie.Type.values:
            data["type_marchandise"] = ArticleExpedie.Type.GENERAL
        return data
    except ai.IAIndisponible:
        t = texte.lower()
        type_trouve = next(
            (typ for typ, mots in MOTS_TYPES.items() if any(m in t for m in mots)), ArticleExpedie.Type.GENERAL
        )
        poids = re.search(r"(\d+(?:[.,]\d+)?)\s?kg", t)
        quantite = re.search(r"(\d+)\s?(cartons?|colis|palettes?|sacs?|caisses?)", t)
        return {
            "designation": texte[:60],
            "type_marchandise": type_trouve,
            "quantite": int(quantite.group(1)) if quantite else 1,
            "poids_kg": float(poids.group(1).replace(",", ".")) if poids else None,
            "interdit": type_trouve == ArticleExpedie.Type.INTERDIT,
        }
