"""Traduit le HTML déjà rendu : libellés de formulaires et textes restés en français."""

import re

from .traductions import traduire

_DECOUPE = re.compile(r"(<[^>]+>)")
_ATTR = re.compile(
    r"""(?P<nom>placeholder|aria-label|title|alt)\s*=\s*(?P<q>["'])(?P<v>.*?)(?P=q)""",
    re.S,
)
_IGNORER = ("script", "style", "textarea")


def traduire_page(reponse, langue):
    type_contenu = reponse.get("Content-Type", "")
    if "text/html" not in type_contenu or getattr(reponse, "streaming", False):
        return
    charset = reponse.charset or "utf-8"
    try:
        html = reponse.content.decode(charset)
    except UnicodeError:
        return
    traduit = _remplacer(html, langue)
    if traduit == html:
        return
    reponse.content = traduit.encode(charset)
    if "Content-Length" in reponse:
        reponse["Content-Length"] = str(len(reponse.content))


def _remplacer(html, langue):
    morceaux = []
    ignorer = 0
    for morceau in _DECOUPE.split(html):
        if morceau.startswith("<"):
            nom = _nom_balise(morceau)
            if nom in _IGNORER and not morceau.startswith("</"):
                ignorer += 1
            elif nom in _IGNORER and morceau.startswith("</") and ignorer:
                ignorer -= 1
            elif not ignorer:
                morceau = _traduire_attributs(morceau, langue)
            morceaux.append(morceau)
        elif ignorer:
            morceaux.append(morceau)
        else:
            morceaux.append(_traduire_texte(morceau, langue))
    return "".join(morceaux)


def _nom_balise(balise):
    correspondance = re.match(r"</?\s*([a-zA-Z0-9]+)", balise)
    return correspondance.group(1).lower() if correspondance else ""


def _traduire_texte(texte, langue):
    debut = len(texte) - len(texte.lstrip())
    fin = len(texte.rstrip())
    if fin <= debut:
        return texte
    coeur = texte[debut:fin]
    cle = " ".join(coeur.split())
    traduit = traduire(cle, langue)
    if traduit == cle:
        return texte
    return texte[:debut] + traduit + texte[fin:]


def _traduire_attributs(balise, langue):
    def remplacer(correspondance):
        valeur = correspondance.group("v")
        traduit = traduire(valeur, langue)
        if traduit == valeur:
            return correspondance.group(0)
        return f"{correspondance.group('nom')}={correspondance.group('q')}{traduit}{correspondance.group('q')}"

    return _ATTR.sub(remplacer, balise)
