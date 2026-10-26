from django import template

from apps.core.traductions import traduire

register = template.Library()


@register.simple_tag(takes_context=True)
def tr(context, texte):
    """Traduit un libellé selon la langue choisie. Le français est le texte source."""
    request = context.get("request")
    langue = getattr(request, "LANGUAGE_CODE", "fr") if request else "fr"
    return traduire(texte, langue)


@register.simple_tag(takes_context=True)
def url_retour(context):
    """Page courante après le choix de langue. Une expédition refusée n'est pas recopiée."""
    request = context.get("request")
    if request is None:
        return ""
    params = request.GET.copy()
    brut = params.get("expedition")
    acceptee = context.get("expedition_id")
    if brut is not None and "expedition_id" in context and str(acceptee or "") != str(brut):
        del params["expedition"]
    query = params.urlencode()
    return f"{request.path}?{query}" if query else request.path


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
