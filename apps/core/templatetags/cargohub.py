from django import template

from apps.core.traductions import traduire

register = template.Library()


@register.simple_tag(takes_context=True)
def tr(context, texte):
    """Traduit un libellé selon la langue choisie. Le français est le texte source."""
    request = context.get("request")
    langue = getattr(request, "LANGUAGE_CODE", "fr") if request else "fr"
    return traduire(texte, langue)


@register.filter
def attr(obj, nom):
    """{{ objet|attr:"champ" }} — lit un attribut, y compris get_FOO_display pour les choix."""
    affichage = getattr(obj, f"get_{nom}_display", None)
    if callable(affichage):
        return affichage()
    valeur = obj
    for morceau in nom.split("__"):
        valeur = getattr(valeur, morceau, "")
        if valeur is None:
            return "—"
    return valeur() if callable(valeur) else valeur
