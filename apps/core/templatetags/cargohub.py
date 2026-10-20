from django import template

register = template.Library()


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
