"""Vérification des marchandises. Gemini propose, les règles CargoHub décident."""

import hashlib
import json
import logging
import re
import time

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.urls import reverse
from django.utils import timezone
from pydantic import BaseModel, Field, ValidationError

from apps.bookings.models import Notification

from ..models import ControleArticle, Expedition, RegleInterdite

logger = logging.getLogger(__name__)

MESSAGE_INDISPONIBLE = (
    "La vérification automatique est indisponible. La demande n'a pas été publiée. Vous pouvez réessayer."
)


class VerificationIndisponible(Exception):
    """Gemini ne répond pas, ou sa réponse n'est pas exploitable. La demande reste non publiée."""


class ArticleIA(BaseModel):
    identifiant: int
    nom: str
    categorie_declaree: str
    categorie_proposee: str = ""
    risque: str
    suspicion: bool
    verification_manuelle: bool
    motif: str = ""
    informations: str = ""

    def risque_normalise(self):
        risque = self.risque.upper()
        if risque not in ControleArticle.Risque.values:
            return ControleArticle.Risque.INCONNU
        return risque


class ReponseIA(BaseModel):
    articles: list[ArticleIA] = Field(default_factory=list)


def calculer_empreinte(articles):
    brut = [
        {
            "id": article.pk,
            "nom": article.designation.strip(),
            "description": (article.description or "").strip(),
            "categorie": article.type_marchandise,
        }
        for article in sorted(articles, key=lambda item: item.pk)
    ]
    return hashlib.sha256(json.dumps(brut, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def _mot_present(mot, texte):
    return re.search(rf"(?<!\w){re.escape(mot)}(?!\w)", texte, flags=re.IGNORECASE) is not None


def regle_confirmee(article, regles):
    """Une interdiction n'est confirmée que par une règle active, pas par le seul avis de l'IA."""
    texte = f"{article.designation} {article.description or ''}"
    for regle in regles:
        if regle.actif and any(_mot_present(mot, texte) for mot in regle.mots()):
            return regle
    return None


def metriques_interdiction(attendus, predits):
    """Précision, rappel et F1 du refus, plus la matrice de confusion des trois statuts."""
    etiquettes = (Expedition.Statut.PUBLIEE, Expedition.Statut.A_VERIFIER, Expedition.Statut.REFUSEE)
    vp = sum(attendu == predit == Expedition.Statut.REFUSEE for attendu, predit in zip(attendus, predits, strict=True))
    fp = sum(
        predit == Expedition.Statut.REFUSEE and attendu != predit
        for attendu, predit in zip(attendus, predits, strict=True)
    )
    fn = sum(
        attendu == Expedition.Statut.REFUSEE and attendu != predit
        for attendu, predit in zip(attendus, predits, strict=True)
    )
    precision = vp / (vp + fp) if vp + fp else 0
    rappel = vp / (vp + fn) if vp + fn else 0
    f1 = 2 * precision * rappel / (precision + rappel) if precision + rappel else 0
    matrice = {attendu: {predit: 0 for predit in etiquettes} for attendu in etiquettes}
    for attendu, predit in zip(attendus, predits, strict=True):
        matrice[attendu][predit] += 1
    return {"precision": precision, "rappel": rappel, "f1": f1, "matrice": matrice}


def conclure(articles, regles, avis_ia):
    """Décision Django. Un risque élevé sans règle correspondante part en vérification humaine."""
    avis = {item.identifiant: item for item in avis_ia}
    lignes = []
    for article in articles:
        ia = avis.get(article.pk)
        regle = regle_confirmee(article, regles)
        if regle is not None:
            decision = ControleArticle.Decision.REFUSE
            motif = regle.motif
        elif ia and (
            ia.suspicion or ia.verification_manuelle or ia.risque_normalise() != ControleArticle.Risque.FAIBLE
        ):
            decision = ControleArticle.Decision.A_VERIFIER
            motif = ia.motif or "Les informations ne permettent pas de confirmer que l'article est autorisé."
        else:
            decision = ControleArticle.Decision.AUTORISE
            motif = ia.motif if ia else ""
        lignes.append(
            {
                "article": article,
                "ia": ia,
                "regle": regle,
                "decision": decision,
                "motif": motif,
            }
        )
    if any(ligne["decision"] == ControleArticle.Decision.REFUSE for ligne in lignes):
        statut = Expedition.Statut.REFUSEE
    elif any(ligne["decision"] == ControleArticle.Decision.A_VERIFIER for ligne in lignes):
        statut = Expedition.Statut.A_VERIFIER
    else:
        statut = Expedition.Statut.PUBLIEE
    return statut, lignes


def _parser(texte, articles):
    try:
        debut, fin = texte.find("{"), texte.rfind("}")
        reponse = ReponseIA.model_validate_json(texte[debut : fin + 1])
    except (ValidationError, ValueError) as exc:
        raise VerificationIndisponible(MESSAGE_INDISPONIBLE) from exc
    attendus = {article.pk for article in articles}
    recus = {item.identifiant for item in reponse.articles}
    if recus != attendus:
        raise VerificationIndisponible(MESSAGE_INDISPONIBLE)
    return reponse.articles


def appeler_gemini(articles, regles):
    """Un seul appel pour tous les articles. La clé reste côté serveur."""
    try:
        from google import genai
        from google.genai import types
    except ImportError as exc:
        raise VerificationIndisponible(MESSAGE_INDISPONIBLE) from exc

    regles_actives = [regle.nom for regle in regles if regle.actif]
    contenu = [
        {
            "identifiant": article.pk,
            "nom": article.designation,
            "description": article.description,
            "categorie_declaree": article.type_marchandise,
        }
        for article in articles
    ]
    consigne = (
        "Tu classes des marchandises pour CargoHub. Tu n'es pas une source réglementaire. "
        "Une suspicion n'est pas une interdiction. Réponds uniquement en JSON : "
        '{"articles":[{"identifiant":int,"nom":str,"categorie_declaree":str,"categorie_proposee":str,'
        '"risque":"FAIBLE|MOYEN|ELEVE|INCONNU","suspicion":bool,"verification_manuelle":bool,'
        '"motif":str,"informations":str}]}. '
        "Reprend chaque identifiant reçu, sans en ajouter ni en retirer. "
        f"Règles CargoHub actives : {regles_actives}. Articles : {json.dumps(contenu, ensure_ascii=False)}"
    )
    client = genai.Client(
        api_key=settings.GEMINI_API_KEY,
        http_options=types.HttpOptions(timeout=20_000),
    )
    debut = time.perf_counter()
    try:
        reponse = client.models.generate_content(
            model=settings.GEMINI_MODEL,
            contents=consigne,
            config=types.GenerateContentConfig(temperature=0, response_mime_type="application/json"),
        )
        texte = reponse.text or ""
    except Exception as exc:
        logger.warning("Gemini indisponible après %d ms", (time.perf_counter() - debut) * 1000)
        raise VerificationIndisponible(MESSAGE_INDISPONIBLE) from exc
    duree = int((time.perf_counter() - debut) * 1000)
    logger.info("Vérification Gemini en %d ms", duree)
    return _parser(texte, articles), duree


def _motif_expedition(statut, expedition, lignes):
    refuses = [ligne for ligne in lignes if ligne["decision"] == ControleArticle.Decision.REFUSE]
    if statut == Expedition.Statut.REFUSEE:
        morceaux = [
            f"l'article {ligne['article'].designation} ({ligne['regle'].nom} : {ligne['motif']})" for ligne in refuses
        ]
        return (
            f"Votre expédition {expedition.reference} a été refusée, car {', '.join(morceaux)}. "
            "Veuillez retirer ou corriger cet article avant de soumettre une nouvelle demande."
        )
    if statut == Expedition.Statut.A_VERIFIER:
        return "Votre expédition nécessite une vérification supplémentaire."
    return ""


def _notifier(expedition, titre, message):
    lien = reverse("shipments:detail", args=[expedition.pk])
    if Notification.objects.filter(destinataire=expedition.pme, titre=titre, message=message).exists():
        return
    Notification.objects.create(destinataire=expedition.pme, titre=titre, message=message, lien=lien)
    send_mail(f"[CargoHub] {titre}", message, None, [expedition.pme.email], fail_silently=True)


def trancher_verification(expedition, *, acceptee, motif):
    """Décision humaine sur une demande en attente. Met à jour le statut et prévient la PME."""
    if acceptee:
        expedition.statut = Expedition.Statut.PUBLIEE
        expedition.motif_decision = f"Votre expédition {expedition.reference} a été acceptée après vérification."
        titre = "Expédition acceptée"
        message = (
            f"Votre demande {expedition.reference} a été acceptée.\n"
            "Elle est maintenant publiée et disponible pour les transporteurs."
        )
        decision = ControleArticle.Decision.AUTORISE
        motif_article = "Accepté après vérification manuelle."
    else:
        expedition.statut = Expedition.Statut.REFUSEE
        expedition.motif_decision = motif
        titre = "Expédition refusée"
        message = (
            f"Votre demande {expedition.reference} a été refusée.\n"
            f"Motif : {motif}\n"
            "Action : veuillez corriger ou retirer l'article concerné et soumettre à nouveau votre demande."
        )
        decision = ControleArticle.Decision.REFUSE
        motif_article = motif
    expedition.save(update_fields=["statut", "motif_decision", "updated_at"])
    if expedition.verifie_le is not None:
        expedition.controles.filter(verifie_le=expedition.verifie_le).update(decision=decision, motif=motif_article)
    _notifier(expedition, titre, message)
    return expedition


def _notifier_refus(expedition, lignes):
    refuses = [ligne["article"].designation for ligne in lignes if ligne["decision"] == ControleArticle.Decision.REFUSE]
    message = (
        f"Votre demande {expedition.reference} a été refusée.\n"
        f"Article concerné : {', '.join(refuses)}\n"
        f"Motif : {expedition.motif_decision}\n"
        "Action : veuillez corriger ou retirer l'article concerné et soumettre à nouveau votre demande."
    )
    _notifier(expedition, "Expédition refusée", message)


@transaction.atomic
def appliquer_verification(expedition):
    """Analyse la version actuelle des articles. Le même contenu n'appelle pas Gemini deux fois."""
    expedition = Expedition.objects.select_for_update().get(pk=expedition.pk)
    articles = list(expedition.articles.all())
    empreinte = calculer_empreinte(articles)
    deja_decidee = expedition.statut in {
        Expedition.Statut.PUBLIEE,
        Expedition.Statut.REFUSEE,
        Expedition.Statut.A_VERIFIER,
    }
    if expedition.empreinte_verification == empreinte and deja_decidee:
        return expedition

    regles = list(RegleInterdite.objects.all())
    duree = 0
    avis = []
    if settings.GEMINI_API_KEY:
        avis, duree = appeler_gemini(articles, regles)
    statut, lignes = conclure(articles, regles, avis)
    moment = timezone.now()
    ControleArticle.objects.bulk_create(
        [
            ControleArticle(
                expedition=expedition,
                article=ligne["article"],
                identifiant_article=ligne["article"].pk,
                nom=ligne["article"].designation,
                categorie_declaree=ligne["article"].type_marchandise,
                categorie_proposee=ligne["ia"].categorie_proposee if ligne["ia"] else "",
                risque=ligne["ia"].risque_normalise() if ligne["ia"] else ControleArticle.Risque.INCONNU,
                suspicion=bool(ligne["ia"] and ligne["ia"].suspicion),
                verification_manuelle=bool(ligne["ia"] and ligne["ia"].verification_manuelle),
                motif=ligne["motif"],
                informations=ligne["ia"].informations if ligne["ia"] else "",
                decision=ligne["decision"],
                regle=ligne["regle"],
                verifie_le=moment,
            )
            for ligne in lignes
        ]
    )
    expedition.statut = statut
    expedition.motif_decision = _motif_expedition(statut, expedition, lignes)
    expedition.empreinte_verification = empreinte
    expedition.verifie_le = moment
    expedition.duree_verification_ms = duree
    expedition.save(
        update_fields=[
            "statut",
            "motif_decision",
            "empreinte_verification",
            "verifie_le",
            "duree_verification_ms",
            "updated_at",
        ]
    )
    if statut == Expedition.Statut.REFUSEE:
        _notifier_refus(expedition, lignes)
    return expedition
