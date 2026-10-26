"""Smart Warehouse Recommender.

Sentence Transformers compare le trajet de l'expédition aux fiches d'entrepôts.
La capacité, les horaires et le statut actif sont décidés par Django, pas par le modèle.
Si le modèle ne se charge pas, un classement lexical prend le relais.
"""

import re
import time
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from datetime import time as heure_jour
from decimal import Decimal
from math import sqrt

from django.conf import settings
from django.utils import timezone
from django.utils.formats import number_format

from apps.shipments.models import Expedition
from apps.warehouses.models import Entrepot
from apps.warehouses.services.capacity import disponible, peut_accueillir, volume_expedition
from apps.warehouses.services.distance import distance_km
from apps.warehouses.services.reservation import STATUTS_ELIGIBLES, depot_pour_affichage
from apps.warehouses.services.villes import centre_ville

NOMBRE = 3
_MODELE = None


class ModeleIndisponible(Exception):
    """Le modèle Sentence Transformers ne peut pas être chargé."""


@dataclass
class Recommandation:
    entrepot: Entrepot
    distance: float | None
    disponible: Decimal
    score: int
    explication: str


def recommander(utilisateur, expedition_id, jour=None):
    """Renvoie les 3 entrepôts éligibles les plus adaptés à l'expédition."""
    debut = time.perf_counter()
    expedition = _expedition(utilisateur, expedition_id)
    if expedition is None:
        return _echec("Expédition inconnue.")
    if depot_pour_affichage(expedition) is not None:
        return _echec("Cette expédition a déjà un dépôt réservé.")
    jour = jour or expedition.date_souhaitee
    if jour < timezone.localdate():
        return _echec("La date de dépôt ne peut pas être dans le passé.")
    volume = volume_expedition(expedition)
    origine = _origine(expedition)
    candidats = []
    for entrepot in Entrepot.objects.filter(actif=True).order_by("nom"):
        if not _ouvert(entrepot):
            continue
        moment = _instant(jour)
        if not peut_accueillir(entrepot, volume, maintenant=moment):
            continue
        candidats.append(entrepot)
    if not candidats:
        return _echec("Aucun entrepôt actif n'a la capacité et les horaires demandés.", expedition, jour)
    fiches = [_fiche(entrepot) for entrepot in candidats]
    demande = _demande(expedition, volume)
    try:
        notes = _similarites_modele(demande, fiches)
        modele = "sentence-transformers"
    except ModeleIndisponible:
        notes = [_similarite_lexicale(demande, fiche) for fiche in fiches]
        modele = "repli"
    lignes = []
    for entrepot, note in zip(candidats, notes, strict=True):
        km = _distance(origine, entrepot)
        score = _score(note, km)
        score = min(100, score + _bonus_trajet(entrepot, expedition))
        moment = _instant(jour)
        reste = disponible(entrepot, maintenant=moment)
        lignes.append(
            Recommandation(
                entrepot=entrepot,
                distance=km,
                disponible=reste,
                score=score,
                explication=_explication(entrepot, expedition, km, reste, volume, origine),
            )
        )
    lignes.sort(key=lambda ligne: (-ligne.score, ligne.distance is None, ligne.distance or 0, ligne.entrepot.nom))
    return {
        "recommandations": lignes[:NOMBRE],
        "erreur": "",
        "expedition": expedition,
        "jour": jour,
        "modele": modele,
        "duree_ms": int((time.perf_counter() - debut) * 1000),
    }


def _echec(message, expedition=None, jour=None):
    return {
        "recommandations": [],
        "erreur": message,
        "expedition": expedition,
        "jour": jour,
        "modele": "",
        "duree_ms": 0,
    }


def vers_json(resultat):
    """Forme transportable vers le worker. Les objets Django n'y entrent pas."""
    jour = resultat["jour"]
    expedition = resultat["expedition"]
    return {
        "erreur": resultat["erreur"],
        "expedition_id": expedition.pk if expedition is not None else None,
        "jour": jour.isoformat() if jour else "",
        "modele": resultat["modele"],
        "duree_ms": resultat["duree_ms"],
        "recommandations": [
            {
                "entrepot_id": ligne.entrepot.pk,
                "distance": ligne.distance,
                "disponible": str(ligne.disponible),
                "score": ligne.score,
                "explication": ligne.explication,
            }
            for ligne in resultat["recommandations"]
        ],
    }


def depuis_json(payload):
    """Reconstruit le résultat à partir des identifiants, pour le template."""
    identifiants = [ligne["entrepot_id"] for ligne in payload["recommandations"]]
    entrepots = {entrepot.pk: entrepot for entrepot in Entrepot.objects.filter(pk__in=identifiants)}
    lignes = []
    for ligne in payload["recommandations"]:
        entrepot = entrepots.get(ligne["entrepot_id"])
        if entrepot is None:
            continue
        lignes.append(
            Recommandation(
                entrepot=entrepot,
                distance=ligne["distance"],
                disponible=Decimal(ligne["disponible"]),
                score=ligne["score"],
                explication=ligne["explication"],
            )
        )
    expedition = None
    if payload.get("expedition_id"):
        expedition = Expedition.objects.filter(pk=payload["expedition_id"]).first()
    jour = None
    if payload.get("jour"):
        jour = datetime.strptime(payload["jour"], "%Y-%m-%d").date()
    return {
        "recommandations": lignes,
        "erreur": payload.get("erreur") or "",
        "expedition": expedition,
        "jour": jour,
        "modele": payload.get("modele") or "",
        "duree_ms": payload.get("duree_ms") or 0,
    }


def _expedition(utilisateur, expedition_id):
    if not str(expedition_id or "").isdigit():
        return None
    return (
        Expedition.objects.filter(pk=int(expedition_id), pme=utilisateur, statut__in=STATUTS_ELIGIBLES)
        .select_related("adresse_depart", "adresse_arrivee")
        .first()
    )


def _origine(expedition):
    """Point de référence du dépôt : GPS de l'adresse, sinon centre de la ville."""
    for adresse in (expedition.adresse_depart, expedition.adresse_arrivee):
        if adresse.latitude is not None and adresse.longitude is not None:
            return {"latitude": adresse.latitude, "longitude": adresse.longitude, "approximatif": False, "ville": ""}
        centre = centre_ville(adresse.ville) or centre_ville(adresse.gouvernorat)
        if centre is not None:
            return {
                "latitude": centre[0],
                "longitude": centre[1],
                "approximatif": True,
                "ville": adresse.ville or adresse.gouvernorat,
            }
    return None


def _distance(origine, entrepot):
    if origine is None or entrepot.latitude is None or entrepot.longitude is None:
        return None
    return distance_km(origine["latitude"], origine["longitude"], entrepot.latitude, entrepot.longitude)


def _instant(jour):
    moment = timezone.make_aware(datetime.combine(jour, heure_jour(12, 0)))
    if moment < timezone.now():
        return timezone.now()
    return moment


def _ouvert(entrepot):
    return entrepot.horaire_fermeture > entrepot.horaire_ouverture


def _fiche(entrepot):
    return (
        f"{entrepot.nom}. {entrepot.description} {entrepot.adresse}, {entrepot.ville}, {entrepot.gouvernorat}. "
        f"Ouvert de {entrepot.horaire_ouverture:%H:%M} à {entrepot.horaire_fermeture:%H:%M}. "
        f"Capacité {entrepot.capacite_max_m3} m3."
    )


def _demande(expedition, volume):
    depart = expedition.adresse_depart.ville
    arrivee = expedition.adresse_arrivee.ville
    texte = f"Expédition de {depart} vers {arrivee}. Volume {volume} m3."
    description = (expedition.description or "").strip()
    if description:
        return f"{texte} {description}"
    return texte


def _charger_modele():
    global _MODELE
    if not getattr(settings, "SENTENCE_TRANSFORMERS_ACTIF", True):
        raise ModeleIndisponible("Le modèle est désactivé.")
    if _MODELE is None:
        try:
            from sentence_transformers import SentenceTransformer

            _MODELE = SentenceTransformer(
                settings.SENTENCE_TRANSFORMERS_MODEL,
                local_files_only=True,
            )
        except Exception as exc:
            raise ModeleIndisponible("Sentence Transformers est indisponible.") from exc
    return _MODELE


def _similarites_modele(demande, fiches):
    modele = _charger_modele()
    vecteurs = modele.encode([demande, *fiches], normalize_embeddings=True)
    return [_cosinus(vecteurs[0], vecteur) for vecteur in vecteurs[1:]]


def _cosinus(gauche, droite):
    produit = sum(float(a) * float(b) for a, b in zip(gauche, droite, strict=False))
    norme_a = sqrt(sum(float(a) * float(a) for a in gauche))
    norme_b = sqrt(sum(float(b) * float(b) for b in droite))
    if norme_a == 0 or norme_b == 0:
        return 0.0
    return max(0.0, min(1.0, produit / (norme_a * norme_b)))


def _similarite_lexicale(demande, fiche):
    mots_demande = _mots(demande)
    mots_fiche = _mots(fiche)
    if not mots_demande or not mots_fiche:
        return 0.0
    return len(mots_demande & mots_fiche) / len(mots_demande)


def _mots(texte):
    return {mot for mot in re.findall(r"[a-z0-9]{3,}", _plier(texte)) if mot not in {"dans", "pour", "avec", "vers"}}


def _plier(texte):
    decompose = unicodedata.normalize("NFD", texte.casefold())
    return "".join(caractere for caractere in decompose if unicodedata.category(caractere) != "Mn")


def _score(similarite, distance):
    note = max(0.0, min(1.0, similarite))
    if distance is None:
        return round(note * 100)
    proximite = max(0.0, 1 - min(distance, 500) / 500)
    return round((note * 0.45 + proximite * 0.55) * 100)


def _explication(entrepot, expedition, distance, reste, volume, origine):
    phrases = [
        f"{_m3(reste)} m³ disponibles, suffisants pour {_m3(volume)} m³.",
        f"Ouvert de {entrepot.horaire_ouverture:%H:%M} à {entrepot.horaire_fermeture:%H:%M}.",
    ]
    if distance is not None and origine is not None and origine["approximatif"]:
        phrases.append(
            f"Environ {distance:.0f} km à vol d'oiseau du centre de {origine['ville']}. "
            "L'adresse n'a pas de coordonnées GPS."
        )
    elif distance is not None:
        phrases.append(f"{distance:.1f} km à vol d'oiseau du lieu connu de l'expédition.")
    elif origine is None:
        phrases.append("La distance n'est pas calculée : l'expédition n'a pas de coordonnées.")
    if _plier(entrepot.ville) == _plier(expedition.adresse_depart.ville):
        phrases.append(f"{entrepot.ville} est la ville de départ.")
    elif _ville_sur_trajet(entrepot, expedition):
        phrases.append(f"La ville {entrepot.ville} est sur le trajet de l'expédition.")
    return " ".join(phrases)


def _m3(valeur):
    return number_format(valeur, decimal_pos=3)


def _bonus_trajet(entrepot, expedition):
    ville = _plier(entrepot.ville).strip()
    if len(ville) < 3:
        return 0
    if ville == _plier(expedition.adresse_depart.ville):
        return 18
    if ville == _plier(expedition.adresse_arrivee.ville):
        return 8
    return 0


def _ville_sur_trajet(entrepot, expedition):
    nom = _plier(entrepot.ville).strip()
    if len(nom) < 3:
        return False
    villes = {_plier(expedition.adresse_depart.ville), _plier(expedition.adresse_arrivee.ville)}
    return nom in villes
