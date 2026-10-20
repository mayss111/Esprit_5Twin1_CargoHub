"""
Partie IA du Membre 5 — Analyse des avis.

1. analyser_sentiment(commentaire, note) : classe chaque avis en POSITIF,
   NEUTRE ou NEGATIF et repère les avis où la note et le texte se contredisent.
2. resumer_avis(avis) : résumé en 2 phrases des avis d'un transporteur,
   affiché sur son profil et dans le back-office.
"""

from apps.core import ai

from .models import Avis

MOTS_NEGATIFS = ["retard", "abîmé", "cassé", "impoli", "jamais", "perdu", "sale"]
MOTS_POSITIFS = ["rapide", "parfait", "ponctuel", "soigneux", "merci", "excellent", "bien"]


def analyser_sentiment(commentaire: str, note: int) -> str:
    try:
        data = ai.demander_json(
            f"Avis client (note {note}/5) : « {commentaire} ». Quel est le sentiment ?",
            systeme='Format : {"sentiment": "POSITIF" | "NEUTRE" | "NEGATIF"}',
        )
        if data.get("sentiment") in Avis.Sentiment.values:
            return data["sentiment"]
    except ai.IAIndisponible:
        pass
    texte = (commentaire or "").lower()
    score = (note - 3) + sum(m in texte for m in MOTS_POSITIFS) - sum(m in texte for m in MOTS_NEGATIFS)
    if score > 0:
        return Avis.Sentiment.POSITIF
    if score < 0:
        return Avis.Sentiment.NEGATIF
    return Avis.Sentiment.NEUTRE


def resumer_avis(avis_qs) -> str:
    commentaires = [a.commentaire for a in avis_qs if a.commentaire][:30]
    if not commentaires:
        return "Pas encore d’avis."
    try:
        return ai.demander("Résume en 2 phrases ces avis sur un transporteur :\n- " + "\n- ".join(commentaires))
    except ai.IAIndisponible:
        notes = [a.note for a in avis_qs]
        return f"{len(notes)} avis, note moyenne {sum(notes) / len(notes):.1f}/5."
