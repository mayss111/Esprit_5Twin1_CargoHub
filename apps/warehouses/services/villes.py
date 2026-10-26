"""Centres des villes tunisiennes, utilisés seulement si l'adresse n'a pas de GPS."""

import unicodedata

CENTRES = {
    "ariana": (36.8625, 10.1956),
    "beja": (36.7333, 9.1833),
    "ben arous": (36.7533, 10.2222),
    "bizerte": (37.2744, 9.8739),
    "ezzahra": (36.7450, 10.3050),
    "gabes": (33.8833, 10.1167),
    "gafsa": (34.4250, 8.7842),
    "jendouba": (36.5011, 8.7803),
    "kairouan": (35.6781, 10.0963),
    "kasserine": (35.1676, 8.8365),
    "kebili": (33.7044, 8.9690),
    "la manouba": (36.8078, 10.1011),
    "la soukra": (36.8830, 10.2450),
    "le kef": (36.1742, 8.7049),
    "mahdia": (35.5047, 11.0622),
    "medenine": (33.3549, 10.5055),
    "monastir": (35.7770, 10.8262),
    "nabeul": (36.4561, 10.7376),
    "oued ellil": (36.8360, 10.0400),
    "raoued": (36.9500, 10.1900),
    "sfax": (34.7406, 10.7603),
    "sidi bouzid": (35.0381, 9.4858),
    "siliana": (36.0847, 9.3708),
    "sousse": (35.8256, 10.6369),
    "tataouine": (32.9297, 10.4518),
    "tozeur": (33.9197, 8.1335),
    "tunis": (36.8065, 10.1815),
    "zaghouan": (36.4028, 10.1428),
}


def centre_ville(nom):
    """Renvoie (latitude, longitude) du centre, ou None si la ville est inconnue."""
    cle = _plier(nom or "")
    return CENTRES.get(cle)


def _plier(texte):
    decompose = unicodedata.normalize("NFD", texte.casefold())
    return "".join(caractere for caractere in decompose if unicodedata.category(caractere) != "Mn")
