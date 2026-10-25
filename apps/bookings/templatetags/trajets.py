from django import template

register = template.Library()


@register.filter
def itineraire(trajet):
    """{{ trajet|itineraire }} → « Sfax → Tunis, via Monastir » : montre pourquoi le trajet convient à l'envoi."""
    if not trajet:
        return "—"
    texte = f"{trajet.ville_depart} → {trajet.ville_arrivee}"
    etapes = [e.ville for e in trajet.etapes.all()]  # triées par « ordre » (Meta du modèle EtapeTrajet)
    return f"{texte}, via {', '.join(etapes)}" if etapes else texte
