"""Import d'expéditions. Chaque ligne est publiée par le contrôleur déjà utilisé à la main.

Rien n'est enregistré si une ligne est invalide. Une ligne valide est ensuite
publiée, refusée ou mise à vérifier par AI Cargo Checker et les règles admin.
"""

import csv
import io
import unicodedata
from collections import Counter
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from django.db import transaction
from openpyxl import Workbook, load_workbook

from apps.shipments.forms import GOUVERNORATS, SaisieExpedition
from apps.shipments.models import ArticleExpedie, Expedition

MAX_OCTETS = 2 * 1024 * 1024
MAX_LIGNES = 200
COLONNES = (
    "date_depart",
    "date_arrivee",
    "description",
    "depart_rue",
    "depart_ville",
    "depart_gouvernorat",
    "depart_code_postal",
    "arrivee_rue",
    "arrivee_ville",
    "arrivee_gouvernorat",
    "arrivee_code_postal",
    "article",
    "description_article",
    "categorie",
    "quantite",
    "poids_kg",
    "volume_m3",
    "fragile",
    "valeur_declaree",
    "groupe",
)
OBLIGATOIRES = (
    "date_depart",
    "date_arrivee",
    "description",
    "depart_rue",
    "depart_ville",
    "depart_gouvernorat",
    "arrivee_rue",
    "arrivee_ville",
    "arrivee_gouvernorat",
    "article",
    "description_article",
    "quantite",
    "poids_kg",
    "volume_m3",
)
CHAMPS_EXPEDITION = (
    "date_depart",
    "date_arrivee",
    "description",
    "depart_rue",
    "depart_ville",
    "depart_gouvernorat",
    "depart_code_postal",
    "arrivee_rue",
    "arrivee_ville",
    "arrivee_gouvernorat",
    "arrivee_code_postal",
)
ALIAS = {
    "date_depart": "date_depart",
    "depart": "date_depart",
    "date_de_depart": "date_depart",
    "date_arrivee": "date_arrivee",
    "arrivee": "date_arrivee",
    "date_d_arrivee": "date_arrivee",
    "description": "description",
    "description_expedition": "description",
    "depart_rue": "depart_rue",
    "rue_depart": "depart_rue",
    "depart_ville": "depart_ville",
    "ville_depart": "depart_ville",
    "depart_gouvernorat": "depart_gouvernorat",
    "gouvernorat_depart": "depart_gouvernorat",
    "depart_code_postal": "depart_code_postal",
    "arrivee_rue": "arrivee_rue",
    "rue_arrivee": "arrivee_rue",
    "arrivee_ville": "arrivee_ville",
    "ville_arrivee": "arrivee_ville",
    "arrivee_gouvernorat": "arrivee_gouvernorat",
    "gouvernorat_arrivee": "arrivee_gouvernorat",
    "arrivee_code_postal": "arrivee_code_postal",
    "article": "article",
    "designation": "article",
    "nom_article": "article",
    "description_article": "description_article",
    "categorie": "categorie",
    "type_marchandise": "categorie",
    "quantite": "quantite",
    "poids_kg": "poids_kg",
    "poids": "poids_kg",
    "volume_m3": "volume_m3",
    "volume": "volume_m3",
    "fragile": "fragile",
    "valeur_declaree": "valeur_declaree",
    "valeur": "valeur_declaree",
    "groupe": "groupe",
}
EXEMPLE = {
    "date_depart": "2026-11-15",
    "date_arrivee": "2026-11-16",
    "description": "Cartons de textile pour un client de Sousse.",
    "depart_rue": "Zone industrielle",
    "depart_ville": "Tunis",
    "depart_gouvernorat": "Tunis",
    "depart_code_postal": "1000",
    "arrivee_rue": "Avenue de la République",
    "arrivee_ville": "Sousse",
    "arrivee_gouvernorat": "Sousse",
    "arrivee_code_postal": "4000",
    "article": "Cartons de vêtements",
    "description_article": "Textile emballé pour le transport.",
    "categorie": "TEXTILE",
    "quantite": "12",
    "poids_kg": "25",
    "volume_m3": "1",
    "fragile": "non",
    "valeur_declaree": "",
    "groupe": "",
}


def contenu_xlsx():
    classeur = Workbook()
    feuille = classeur.active
    feuille.title = "Expeditions"
    feuille.append(list(COLONNES))
    feuille.append([EXEMPLE[colonne] for colonne in COLONNES])
    sortie = io.BytesIO()
    classeur.save(sortie)
    return sortie.getvalue()


def importer(fichier, pme):
    """Retourne (expéditions créées, erreurs). Aucune création si une ligne est invalide."""
    try:
        tableau = _lire(fichier)
    except ValueError as exc:
        return [], [str(exc)]
    if isinstance(tableau, str):
        return [], [tableau]
    prets, erreurs = _valider(tableau, pme)
    if erreurs:
        return [], erreurs
    with transaction.atomic():
        crees = [SaisieExpedition(donnees, pme=pme, publier=True).save() for donnees in prets]
    return crees, []


def message_bilan(expeditions):
    comptes = Counter(expedition.statut for expedition in expeditions)
    libelles = (
        (Expedition.Statut.PUBLIEE, "publiée", "publiées"),
        (Expedition.Statut.REFUSEE, "refusée", "refusées"),
        (Expedition.Statut.A_VERIFIER, "à vérifier", "à vérifier"),
        (Expedition.Statut.BROUILLON, "laissée en brouillon", "laissées en brouillon"),
    )
    morceaux = []
    for statut, singulier, pluriel in libelles:
        nombre = comptes.get(statut, 0)
        if nombre:
            morceaux.append(f"{nombre} {singulier if nombre == 1 else pluriel}")
    total = len(expeditions)
    entete = "1 expédition créée" if total == 1 else f"{total} expéditions créées"
    if not morceaux:
        return entete + "."
    return entete + " : " + ", ".join(morceaux) + "."


def _lire(fichier):
    nom = (getattr(fichier, "name", "") or "").lower()
    if getattr(fichier, "size", 0) > MAX_OCTETS:
        raise ValueError("Le fichier dépasse 2 Mo.")
    contenu = fichier.read()
    if nom.endswith(".csv"):
        return _csv(contenu)
    if nom.endswith(".xlsx"):
        return _xlsx(contenu)
    raise ValueError("Utilisez un fichier Excel .xlsx ou un CSV.")


def _csv(contenu):
    try:
        texte = contenu.decode("utf-8-sig")
    except UnicodeDecodeError:
        texte = contenu.decode("latin-1")
    delimiteur = ";" if texte[:2000].count(";") > texte[:2000].count(",") else ","
    lecteur = csv.DictReader(io.StringIO(texte), delimiter=delimiteur)
    if not lecteur.fieldnames:
        return "Le fichier ne contient pas d'en-tête."
    return _lignes(lecteur.fieldnames, lecteur)


def _xlsx(contenu):
    try:
        classeur = load_workbook(io.BytesIO(contenu), read_only=True, data_only=True)
    except Exception as exc:
        raise ValueError("Le fichier Excel est illisible.") from exc
    feuille = classeur.active
    lignes = feuille.iter_rows(values_only=True)
    try:
        entetes = next(lignes)
    except StopIteration:
        return "Le fichier ne contient pas d'en-tête."
    return _lignes(entetes, lignes)


def _lignes(entetes, lignes):
    colonnes = [_entete(valeur) for valeur in entetes]
    manquantes = [nom for nom in OBLIGATOIRES if nom not in colonnes]
    if manquantes:
        return "Colonnes obligatoires manquantes : " + ", ".join(manquantes) + "."
    resultat = []
    for indice, ligne in enumerate(lignes, start=2):
        valeurs = list(ligne.values()) if hasattr(ligne, "keys") else list(ligne)
        if all(_vide(valeur) for valeur in valeurs):
            continue
        resultat.append({colonnes[i]: valeurs[i] if i < len(valeurs) else "" for i in range(len(colonnes))})
        resultat[-1]["_ligne"] = indice
        if len(resultat) > MAX_LIGNES:
            return f"Le fichier dépasse {MAX_LIGNES} lignes."
    if not resultat:
        return "Le fichier ne contient aucune expédition."
    return resultat


def _valider(tableau, pme):
    groupes = []
    index = {}
    erreurs = []
    for ligne in tableau:
        cle = _texte(ligne.get("groupe")) or f"__ligne_{ligne['_ligne']}"
        if cle not in index:
            index[cle] = len(groupes)
            groupes.append({"ligne": ligne, "articles": [], "numeros": []})
        groupe = groupes[index[cle]]
        conflit = _conflit(groupe["ligne"], ligne)
        if conflit:
            erreurs.append(f"Ligne {ligne['_ligne']} : {conflit}")
            continue
        article, erreur = _article(ligne)
        if erreur:
            erreurs.append(f"Ligne {ligne['_ligne']} : {erreur}")
            continue
        groupe["articles"].append(article)
        groupe["numeros"].append(ligne["_ligne"])
    if erreurs:
        return [], erreurs
    prets = []
    for groupe in groupes:
        donnees = _donnees(groupe["ligne"], groupe["articles"])
        saisie = SaisieExpedition(donnees, pme=pme, publier=True)
        if saisie.is_valid():
            prets.append(donnees)
            continue
        erreurs.append(f"Ligne {', '.join(str(numero) for numero in groupe['numeros'])} : {_message(saisie)}")
    return prets, erreurs


def _donnees(ligne, articles):
    donnees = {
        "generale-date_souhaitee": _date(ligne.get("date_depart")).isoformat(),
        "generale-date_arrivee": _date(ligne.get("date_arrivee")).isoformat(),
        "generale-description": _texte(ligne.get("description")),
        "depart-ligne": _texte(ligne.get("depart_rue")),
        "depart-ville": _texte(ligne.get("depart_ville")),
        "depart-gouvernorat": _gouvernorat(ligne.get("depart_gouvernorat")),
        "depart-code_postal": _texte(ligne.get("depart_code_postal")),
        "arrivee-ligne": _texte(ligne.get("arrivee_rue")),
        "arrivee-ville": _texte(ligne.get("arrivee_ville")),
        "arrivee-gouvernorat": _gouvernorat(ligne.get("arrivee_gouvernorat")),
        "arrivee-code_postal": _texte(ligne.get("arrivee_code_postal")),
        "articles-TOTAL_FORMS": str(len(articles)),
        "articles-INITIAL_FORMS": "0",
        "articles-MIN_NUM_FORMS": "0",
        "articles-MAX_NUM_FORMS": "30",
    }
    for indice, article in enumerate(articles):
        prefixe = f"articles-{indice}-"
        donnees[prefixe + "designation"] = article["designation"]
        donnees[prefixe + "description"] = article["description"]
        donnees[prefixe + "type_marchandise"] = article["categorie"]
        donnees[prefixe + "quantite"] = article["quantite"]
        donnees[prefixe + "poids_kg"] = article["poids_kg"]
        donnees[prefixe + "volume_m3"] = article["volume_m3"]
        donnees[prefixe + "valeur_declaree"] = article["valeur_declaree"]
        if article["fragile"]:
            donnees[prefixe + "fragile"] = "on"
    return donnees


def _article(ligne):
    categorie = _categorie(ligne.get("categorie"))
    if categorie is None:
        return None, "La catégorie est inconnue."
    quantite = _entier(ligne.get("quantite"))
    poids = _decimal(ligne.get("poids_kg"))
    volume = _decimal(ligne.get("volume_m3"))
    if not _texte(ligne.get("article")):
        return None, "Indiquez le nom de l'article."
    if quantite is None or quantite < 1:
        return None, "La quantité doit être supérieure à zéro."
    if poids is None or poids <= 0:
        return None, "Le poids doit être supérieur à zéro."
    if volume is None or volume <= 0:
        return None, "Le volume doit être supérieur à zéro."
    if _date(ligne.get("date_depart")) is None or _date(ligne.get("date_arrivee")) is None:
        return None, "Les dates de départ et d'arrivée doivent être au format AAAA-MM-JJ."
    valeur = _texte(ligne.get("valeur_declaree"))
    if valeur and _decimal(ligne.get("valeur_declaree")) is None:
        return None, "La valeur déclarée n'est pas un nombre."
    return {
        "designation": _texte(ligne.get("article")),
        "description": _texte(ligne.get("description_article")),
        "categorie": categorie,
        "quantite": str(quantite),
        "poids_kg": str(poids),
        "volume_m3": str(volume),
        "valeur_declaree": "" if not valeur else str(_decimal(ligne.get("valeur_declaree"))),
        "fragile": _oui(ligne.get("fragile")),
    }, ""


def _conflit(premiere, suivante):
    if premiere is suivante:
        return ""
    for champ in CHAMPS_EXPEDITION:
        gauche = _texte(premiere.get(champ))
        droite = _texte(suivante.get(champ))
        if gauche and droite and gauche != droite:
            return "Les lignes d'un même groupe doivent décrire la même expédition."
    return ""


def _message(saisie):
    textes = []
    for formulaire in (saisie.generale, saisie.depart, saisie.arrivee, *saisie.articles.forms):
        for erreurs in formulaire.errors.values():
            textes.extend(str(erreur) for erreur in erreurs)
    textes.extend(str(erreur) for erreur in saisie.articles.non_form_errors())
    return " ".join(textes) or "Cette expédition ne peut pas être publiée."


def _entete(valeur):
    clef = _clef(valeur)
    return ALIAS.get(clef, clef)


def _clef(valeur):
    texte = _sans_accent(_texte(valeur)).replace(" ", "_").replace("-", "_")
    return "".join(caractere for caractere in texte if caractere.isalnum() or caractere == "_")


def _sans_accent(texte):
    decompose = unicodedata.normalize("NFD", texte)
    return "".join(caractere for caractere in decompose if unicodedata.category(caractere) != "Mn")


def _texte(valeur):
    if valeur is None:
        return ""
    if isinstance(valeur, float) and valeur.is_integer():
        return str(int(valeur))
    return str(valeur).strip()


def _vide(valeur):
    return valeur is None or str(valeur).strip() == ""


def _date(valeur):
    if isinstance(valeur, datetime):
        return valeur.date()
    if isinstance(valeur, date):
        return valeur
    texte = _texte(valeur)
    if not texte:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(texte[:10], fmt).date()
        except ValueError:
            continue
    return None


def _gouvernorat(valeur):
    connus = {_sans_accent(nom).casefold(): nom for nom, _libelle in GOUVERNORATS}
    return connus.get(_sans_accent(_texte(valeur)).casefold(), _texte(valeur))


def _categorie(valeur):
    texte = _texte(valeur)
    if not texte:
        return ArticleExpedie.Type.GENERAL
    connus = {}
    for code, libelle in ArticleExpedie.Type.choices:
        connus[_sans_accent(code).casefold()] = code
        connus[_sans_accent(libelle).casefold()] = code
    return connus.get(_sans_accent(texte).casefold())


def _entier(valeur):
    texte = _texte(valeur)
    if not texte:
        return None
    try:
        return int(Decimal(texte.replace(",", ".")))
    except (InvalidOperation, ValueError):
        return None


def _decimal(valeur):
    texte = _texte(valeur).replace(",", ".")
    if not texte:
        return None
    try:
        return Decimal(texte)
    except InvalidOperation:
        return None


def _oui(valeur):
    return _sans_accent(_texte(valeur)).casefold() in {"1", "oui", "yes", "true", "vrai", "on"}
