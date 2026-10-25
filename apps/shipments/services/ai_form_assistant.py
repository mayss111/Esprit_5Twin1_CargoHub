"""Smart Shipment Assistant. Préremplit le formulaire, ne publie rien.

Distinct d'AI Cargo Checker : cet appel ne décide pas du statut et ne crée
aucune expédition. La vérification des marchandises reste faite à la publication.
"""

import hashlib
import json
import logging
import re
import time
import unicodedata
from datetime import date, datetime
from decimal import Decimal

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from apps.shipments.forms import GOUVERNORATS
from apps.shipments.models import ArticleExpedie

logger = logging.getLogger(__name__)

MESSAGE_INDISPONIBLE = "L'assistant est momentanément indisponible. Saisissez le formulaire manuellement."
DELAI_CACHE = 600
MOIS = (
    "janvier",
    "fevrier",
    "mars",
    "avril",
    "mai",
    "juin",
    "juillet",
    "aout",
    "septembre",
    "octobre",
    "novembre",
    "decembre",
)
SYNONYMES = {
    "informatique": ArticleExpedie.Type.ELECTRONIQUE,
    "ordinateur": ArticleExpedie.Type.ELECTRONIQUE,
    "ordinateurs": ArticleExpedie.Type.ELECTRONIQUE,
    "ecran": ArticleExpedie.Type.ELECTRONIQUE,
    "ecrans": ArticleExpedie.Type.ELECTRONIQUE,
    "vetement": ArticleExpedie.Type.TEXTILE,
    "vetements": ArticleExpedie.Type.TEXTILE,
    "textile": ArticleExpedie.Type.TEXTILE,
    "alimentaire": ArticleExpedie.Type.ALIMENTAIRE,
    "nourriture": ArticleExpedie.Type.ALIMENTAIRE,
    "materiaux": ArticleExpedie.Type.MATERIAUX,
    "construction": ArticleExpedie.Type.MATERIAUX,
    "general": ArticleExpedie.Type.GENERAL,
    "generale": ArticleExpedie.Type.GENERAL,
}


class AssistantInvalide(Exception):
    """La description envoyée ne peut pas être analysée."""


class AssistantIndisponible(Exception):
    """Gemini n'a pas fourni de réponse exploitable."""


class _AdresseIA(BaseModel):
    model_config = ConfigDict(extra="ignore")
    ligne: str | None = None
    ville: str | None = None
    gouvernorat: str | None = None
    code_postal: str | None = None


class _ArticleIA(BaseModel):
    model_config = ConfigDict(extra="ignore")
    nom: str
    description: str | None = None
    quantite: int | None = None
    unite: str | None = None
    categorie_proposee: str | None = None
    poids_kg: Decimal | None = None
    volume_m3: Decimal | None = None
    valeur_declaree: Decimal | None = None
    fragile: bool | None = None

    @field_validator("quantite", mode="before")
    @classmethod
    def _quantite(cls, valeur):
        if valeur in (None, "") or isinstance(valeur, bool):
            return None
        if isinstance(valeur, float) and not valeur.is_integer():
            return None
        try:
            nombre = int(valeur)
        except (TypeError, ValueError):
            return None
        return nombre if nombre > 0 else None

    @field_validator("fragile", mode="before")
    @classmethod
    def _fragile(cls, valeur):
        if isinstance(valeur, bool):
            return valeur
        return None

    @field_validator("poids_kg", "volume_m3", "valeur_declaree", mode="before")
    @classmethod
    def _decimal(cls, valeur):
        return _decimal_ou_rien(valeur)


class _ReponseIA(BaseModel):
    model_config = ConfigDict(extra="ignore")
    adresse_depart: _AdresseIA = Field(default_factory=_AdresseIA)
    adresse_arrivee: _AdresseIA = Field(default_factory=_AdresseIA)
    date_depart: date | None = None
    date_arrivee: date | None = None
    articles: list[_ArticleIA] = Field(default_factory=list)
    poids_total_declare: Decimal | None = None

    @field_validator("poids_total_declare", mode="before")
    @classmethod
    def _poids(cls, valeur):
        return _decimal_ou_rien(valeur)


def analyser_description(description, user_id, aujourdhui=None):
    """Retourne les champs exploitables. N'écrit rien en base."""
    texte = (description or "").strip()
    if len(texte) < 10:
        raise AssistantInvalide("Décrivez l'expédition en au moins 10 caractères.")
    if len(texte) > 4000:
        raise AssistantInvalide("La description dépasse 4000 caractères.")
    cle = f"shipments-assistant:{user_id}:{hashlib.sha256(texte.encode()).hexdigest()}"
    memorise = cache.get(cle)
    if memorise is not None:
        return {**memorise, "depuis_cache": True}

    brut, duree = generer_json(texte)
    reponse = _charger(brut)
    resultat = _valider(reponse, texte, aujourdhui or timezone.localdate())
    resultat["duree_ms"] = duree
    resultat["depuis_cache"] = False
    cache.set(cle, resultat, DELAI_CACHE)
    return resultat


def generer_json(description):
    if not settings.GEMINI_API_KEY:
        raise AssistantIndisponible("L'assistant IA n'est pas configuré.")
    try:
        from google import genai
        from google.genai import types
    except ImportError as exc:
        raise AssistantIndisponible(MESSAGE_INDISPONIBLE) from exc

    client = genai.Client(api_key=settings.GEMINI_API_KEY, http_options=types.HttpOptions(timeout=20_000))
    debut = time.perf_counter()
    try:
        reponse = client.models.generate_content(
            model=settings.GEMINI_MODEL,
            contents=_consigne(description),
            config=types.GenerateContentConfig(temperature=0, response_mime_type="application/json"),
        )
        texte = reponse.text or ""
    except Exception as exc:
        duree = int((time.perf_counter() - debut) * 1000)
        logger.warning("Assistant Gemini indisponible (%s) après %d ms", type(exc).__name__, duree)
        raise AssistantIndisponible(MESSAGE_INDISPONIBLE) from exc
    duree = int((time.perf_counter() - debut) * 1000)
    logger.info("Assistant Gemini en %d ms", duree)
    return texte, duree


def _consigne(description):
    categories = ", ".join(f"{code} ({label})" for code, label in ArticleExpedie.Type.choices)
    gouvernorats = ", ".join(valeur for valeur, _label in GOUVERNORATS)
    return (
        "Tu extrais une expédition CargoHub. Tu ne publies rien et tu n'inventes aucune valeur. "
        "Si une information est absente, mets null. "
        "N'invente jamais un poids, un volume ou une valeur déclarée, et ne répartis jamais un total. "
        "Quand le texte donne un poids, un volume ou une valeur par article et par unité, "
        "recopie ce nombre unitaire dans l'article concerné, même s'il est écrit avec une virgule (0,08). "
        "Si seul un total est indiqué, laisse les champs unitaires à null et mets le total dans "
        "poids_total_declare, volume_total_declare ou valeur_totale_declaree. "
        "fragile vaut true si l'article est explicitement fragile, false s'il est explicitement non fragile, "
        "et null si le texte ne le précise pas. "
        "Ne fabrique pas de rue ni de code postal. "
        "Réponds uniquement en JSON avec les clés : "
        "adresse_depart {ligne, ville, gouvernorat, code_postal}, "
        "adresse_arrivee {ligne, ville, gouvernorat, code_postal}, "
        "date_depart (YYYY-MM-DD), date_arrivee (YYYY-MM-DD), "
        "articles [{nom, description, quantite, unite, categorie_proposee, poids_kg, volume_m3, "
        "valeur_declaree, fragile}], "
        "poids_total_declare, volume_total_declare, valeur_totale_declaree. "
        f"Catégories autorisées : {categories}. Gouvernorats : {gouvernorats}. "
        f"Description de la PME : {description}"
    )


def _charger(brut):
    texte = (brut or "").strip()
    if texte.startswith("```"):
        texte = re.sub(r"^```(?:json)?|```$", "", texte, flags=re.IGNORECASE).strip()
    try:
        donnees = json.loads(texte)
    except json.JSONDecodeError as exc:
        raise AssistantIndisponible("La réponse de l'assistant est inutilisable.") from exc
    if not isinstance(donnees, dict):
        raise AssistantIndisponible("La réponse de l'assistant est inutilisable.")
    for cle in ("adresse_depart", "adresse_arrivee"):
        if not isinstance(donnees.get(cle), dict):
            donnees[cle] = {}
    if not isinstance(donnees.get("articles"), list):
        donnees["articles"] = []
    for cle in ("date_depart", "date_arrivee"):
        donnees[cle] = _date_ou_rien(donnees.get(cle))
    try:
        return _ReponseIA.model_validate(donnees)
    except ValidationError as exc:
        raise AssistantIndisponible("La réponse de l'assistant est inutilisable.") from exc


def _valider(reponse, source, aujourdhui):
    champs = {}
    avertissements = []
    manquantes = []
    _adresse_vers_champs(reponse.adresse_depart, "depart", source, champs, manquantes)
    _adresse_vers_champs(reponse.adresse_arrivee, "arrivee", source, champs, manquantes)
    depart = _date_utile(reponse.date_depart, source, aujourdhui, "départ", avertissements)
    arrivee = _date_utile(reponse.date_arrivee, source, aujourdhui, "arrivée", avertissements)
    if depart and arrivee and arrivee < depart:
        avertissements.append("La date d'arrivée précède le départ. Elle n'a pas été recopiée.")
        arrivee = None
    if depart:
        champs["generale-date_souhaitee"] = depart.isoformat()
    else:
        manquantes.append("Date de départ")
    if arrivee:
        champs["generale-date_arrivee"] = arrivee.isoformat()
    else:
        manquantes.append("Date d'arrivée")
    champs["generale-description"] = source

    texte = _texte_mesure(source)
    noms = [(article.nom or "").strip() for article in reponse.articles]
    articles = []
    for article in reponse.articles:
        ligne = _article_utile(article, source, texte, noms, avertissements, manquantes)
        if ligne:
            articles.append(ligne)
    if not articles:
        manquantes.append("Articles")
    if articles and any(ligne["volume_m3"] is None for ligne in articles):
        manquantes.append("Volume des marchandises")
    poids_total = _poids_total(reponse, source, len(articles))
    poids_complets = bool(articles) and all(ligne["poids_kg"] is not None for ligne in articles)
    if poids_total is not None and not poids_complets:
        avertissements.append(
            f"Poids total déclaré : {_nombre(poids_total)} kg. Il n'a pas été réparti entre les articles."
        )
    elif articles and any(ligne["poids_kg"] is None for ligne in articles):
        manquantes.append("Poids des articles")
    return {
        "champs": champs,
        "articles": articles,
        "poids_total_declare": None if poids_complets else _nombre_json(poids_total),
        "totaux": {
            "poids_kg": _total_calcule(articles, "poids_kg"),
            "volume_m3": _total_calcule(articles, "volume_m3"),
            "valeur_declaree": _total_calcule(articles, "valeur_declaree"),
        },
        "informations_manquantes": _uniques(manquantes),
        "avertissements": _uniques(avertissements),
    }


def _adresse_vers_champs(adresse, prefixe, source, champs, manquantes):
    role = "de départ" if prefixe == "depart" else "d'arrivée"
    ville = _texte_present(adresse.ville, source)
    if ville:
        champs[f"{prefixe}-ville"] = ville
        gouvernorat = _gouvernorat(ville) or _gouvernorat(_texte_present(adresse.gouvernorat, source))
        if gouvernorat:
            champs[f"{prefixe}-gouvernorat"] = gouvernorat
        else:
            manquantes.append(f"Gouvernorat {role}")
    else:
        manquantes.append(f"Ville {role}")
    ligne = _texte_present(adresse.ligne, source)
    if ligne and _plier(ligne) != _plier(ville or ""):
        champs[f"{prefixe}-ligne"] = ligne
    else:
        manquantes.append(f"Adresse exacte {role}")
    code = _code_present(adresse.code_postal, source)
    if code:
        champs[f"{prefixe}-code_postal"] = code


def _article_utile(article, source, texte, noms, avertissements, manquantes):
    nom = (article.nom or "").strip()
    if not nom or not _mots_presents(nom, source):
        return None
    zone = _zone_article(nom, texte, noms)
    quantite = _quantite_confirmee(article.quantite, zone)
    if quantite is None:
        manquantes.append(f"Quantité : {nom}")
    fragile = _fragile_article(nom, texte)
    categorie = _categorie(article.categorie_proposee, nom, avertissements, manquantes)
    poids = _mesure_article(article.poids_kg, zone, "kg")
    volume = _mesure_article(article.volume_m3, zone, r"(?:m3|m³)")
    valeur = _mesure_article(article.valeur_declaree, zone, r"(?:dt|dinars?|tnd)")
    unite = _texte_present(article.unite, source)
    description = _texte_present(article.description, source)
    if fragile is None:
        manquantes.append(f"Fragilité : {nom}")
    return {
        "designation": nom,
        "description": description,
        "type_marchandise": categorie,
        "quantite": quantite,
        "poids_kg": _nombre_json(poids),
        "volume_m3": _nombre_json(volume),
        "valeur_declaree": _nombre_json(valeur),
        "fragile": fragile,
        "unite": unite,
    }


def _categorie(proposee, nom, avertissements, manquantes):
    if not proposee:
        manquantes.append(f"Catégorie : {nom}")
        return None
    plie = _plier(proposee)
    for code, label in ArticleExpedie.Type.choices:
        if plie in {_plier(code), _plier(label)}:
            return code
    code = SYNONYMES.get(plie)
    if code:
        avertissements.append(
            f"La catégorie « {proposee.strip()} » est rapprochée de {ArticleExpedie.Type(code).label}."
        )
        return code
    avertissements.append(f"La catégorie « {proposee.strip()} » ne correspond à aucune catégorie CargoHub.")
    manquantes.append(f"Catégorie : {nom}")
    return None


def _date_utile(jour, source, aujourdhui, role, avertissements):
    if jour is None or not _date_mentionnee(jour, source):
        return None
    if jour < aujourdhui:
        avertissements.append(f"La date de {role} indiquée est passée. Elle n'a pas été recopiée.")
        return None
    return jour


def _poids_total(reponse, source, nb_articles):
    texte = _texte_mesure(source)
    mentions = []
    for match in re.finditer(r"(\d+(?:\.\d+)?)\s*kg\b", texte):
        avant = texte[max(0, match.start() - 40) : match.start()]
        mentions.append((Decimal(match.group(1)), _est_total(avant), _est_unitaire(avant)))
    totaux = [valeur for valeur, total, _unitaire in mentions if total]
    if len(totaux) == 1:
        return totaux[0]
    if len(mentions) == 1 and not mentions[0][2] and nb_articles > 1:
        return mentions[0][0]
    if (
        reponse.poids_total_declare is not None
        and reponse.poids_total_declare in {valeur for valeur, _total, _unitaire in mentions}
        and nb_articles > 1
        and not any(_unitaire for _valeur, _total, _unitaire in mentions)
    ):
        return reponse.poids_total_declare
    return None


def _texte_mesure(source):
    """Minuscules sans accent. Seule une virgule décimale devient un point."""
    return re.sub(r"(\d),(\d)", r"\1.\2", _plier(source))


def _ancre(nom, texte):
    mots = [mot for mot in re.split(r"[^a-z0-9]+", _plier(nom)) if len(mot) >= 4]
    positions = []
    for mot in mots:
        positions.extend(match.start() for match in re.finditer(rf"\b{re.escape(mot)}\b", texte))
    return min(positions) if positions else None


def _zone_article(nom, texte, noms):
    ancre = _ancre(nom, texte)
    if ancre is None:
        return ""
    autres = []
    for autre in noms:
        if autre == nom:
            continue
        position = _ancre(autre, texte)
        if position is not None and position != ancre:
            autres.append(position)
    precedente = max((position for position in autres if position < ancre), default=None)
    suivante = min((position for position in autres if position > ancre), default=None)
    debut = 0 if precedente is None else max(precedente + 1, ancre - 40)
    fin = len(texte) if suivante is None else suivante
    return texte[debut:fin]


def _mesure_article(valeur_ia, zone, unite):
    trouves = []
    for match in re.finditer(rf"(\d+(?:\.\d+)?)\s*{unite}(?!\w)", zone):
        avant = zone[max(0, match.start() - 40) : match.start()]
        if _est_total(avant):
            continue
        try:
            valeur = Decimal(match.group(1))
        except Exception:
            continue
        if valeur <= 0:
            continue
        trouves.append((valeur, _est_unitaire(avant)))
    precisees = [valeur for valeur, unitaire in trouves if unitaire]
    candidats = precisees or [valeur for valeur, _unitaire in trouves]
    if len(candidats) == 1:
        return candidats[0]
    if valeur_ia is not None and valeur_ia in candidats:
        return valeur_ia
    return None


def _est_total(avant):
    return re.search(r"\btotal", avant) is not None


def _est_unitaire(avant):
    return re.search(r"\bunitair|\bpar unite|\bchaque\b|\bpar article", avant) is not None


def _quantite_confirmee(quantite, zone):
    if quantite is None:
        return None
    for match in re.finditer(rf"\b{int(quantite)}\b", zone):
        suite = zone[match.end() : match.end() + 12].lstrip()
        if re.match(r"(?:kg|m3|m³|dt|dinars?|tnd)\b", suite):
            continue
        return quantite
    return None


def _fragile_article(nom, texte):
    avis = None
    for phrase in re.split(r"(?<!\d)[.!?](?!\d)", texte):
        ancre = _ancre(nom, phrase)
        if ancre is None or "fragile" not in phrase:
            continue
        portion = phrase[ancre:]
        if re.search(r"\b(?:non|pas)\s+fragiles?\b", portion):
            avis = False
        elif re.search(r"\bfragiles?\b", portion):
            avis = True
    return avis


def _total_calcule(articles, cle):
    if not articles or any(ligne[cle] is None or not ligne["quantite"] for ligne in articles):
        return None
    total = sum((Decimal(str(ligne[cle])) * ligne["quantite"] for ligne in articles), Decimal("0"))
    return _nombre_json(total)


def _decimal_ou_rien(valeur):
    if valeur in (None, "") or isinstance(valeur, bool):
        return None
    if isinstance(valeur, str):
        valeur = valeur.strip().replace("\u00a0", "").replace(" ", "").replace(",", ".")
    try:
        nombre = Decimal(str(valeur))
    except Exception:
        return None
    if not nombre.is_finite() or nombre < 0:
        return None
    return nombre


def _gouvernorat(ville):
    if not ville:
        return None
    cle = _plier(ville)
    for valeur, label in GOUVERNORATS:
        if cle in {_plier(valeur), _plier(label)}:
            return valeur
    return None


def _texte_present(valeur, source):
    texte = (valeur or "").strip()
    if texte and _plier(texte) in _plier(source):
        return texte
    return None


def _code_present(valeur, source):
    texte = re.sub(r"\s+", "", valeur or "")
    if texte and texte in re.sub(r"\s+", "", source):
        return texte
    return None


def _mots_presents(nom, source):
    source_plie = _plier(source)
    mots = [mot for mot in re.split(r"[^a-z0-9]+", _plier(nom)) if len(mot) >= 4]
    return any(mot in source_plie for mot in mots)


def _date_mentionnee(jour, source):
    texte = _plier(source)
    if not re.search(rf"\b{jour.day}\b", texte) or not re.search(rf"\b{jour.year}\b", texte):
        return False
    mois = MOIS[jour.month - 1]
    return mois in texte or re.search(rf"\b{jour.month}\b", texte) is not None


def _date_ou_rien(valeur):
    if valeur in (None, ""):
        return None
    if isinstance(valeur, datetime):
        return valeur.date()
    if isinstance(valeur, date):
        return valeur
    texte = str(valeur).strip()
    for forme in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(texte, forme).date()
        except ValueError:
            continue
    return None


def _plier(texte):
    normalise = unicodedata.normalize("NFD", str(texte).lower())
    return "".join(caractere for caractere in normalise if unicodedata.category(caractere) != "Mn")


def _nombre(valeur):
    texte = format(valeur, "f")
    if "." in texte:
        texte = texte.rstrip("0").rstrip(".")
    return texte or "0"


def _nombre_json(valeur):
    if valeur is None:
        return None
    if valeur == valeur.to_integral():
        return int(valeur)
    texte = format(valeur, "f")
    if "." in texte:
        texte = texte.rstrip("0").rstrip(".")
    return texte or "0"


def _uniques(lignes):
    vus = []
    for ligne in lignes:
        if ligne not in vus:
            vus.append(ligne)
    return vus
