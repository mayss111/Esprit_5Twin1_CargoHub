"""Score de fiabilité déterministe et explication Groq facultative.

Le modèle ne reçoit que des agrégats numériques : aucune adresse, email, nom,
commentaire ou identifiant métier n'est envoyé au fournisseur IA.
"""

import hashlib
import json
import logging
from dataclasses import dataclass

from django.conf import settings
from django.core.cache import cache

from apps.bookings.models import Reservation
from apps.core.roles import Role
from apps.insurance.models import Sinistre
from apps.reclamations.models import Reclamation
from apps.tracking.models import Incident

logger = logging.getLogger(__name__)

EXPIRATION_EXPLICATION = 60 * 60 * 6


@dataclass(frozen=True)
class Fiabilite:
    score: int | None
    explication: str
    details: dict


def _reservations_de(utilisateur):
    if utilisateur.role == Role.PME:
        return Reservation.objects.filter(expedition__pme=utilisateur)
    if utilisateur.role == Role.TRANSPORTEUR:
        return Reservation.objects.filter(trajet__transporteur=utilisateur)
    return Reservation.objects.none()


def _mesures(utilisateur):
    reservations = _reservations_de(utilisateur)
    conclues = reservations.filter(statut__in=[Reservation.Statut.LIVREE, Reservation.Statut.ANNULEE])
    livrees = conclues.filter(statut=Reservation.Statut.LIVREE).count()
    total_conclues = conclues.count()
    retards = Incident.objects.filter(
        reservation__in=reservations,
        type=Incident.Type.RETARD,
        statut=Incident.Statut.RESOLU,
    ).count()
    reclamations = (
        Reclamation.objects.filter(
            expedition__reservations__in=reservations,
            statut=Reclamation.Statut.RESOLUE,
        )
        .distinct()
        .count()
    )
    sinistres = (
        Sinistre.objects.filter(
            expedition__reservations__in=reservations,
            statut__in=[Sinistre.Statut.ACCEPTE, Sinistre.Statut.CLOTURE],
        )
        .distinct()
        .count()
    )
    return {
        "livraisons_reussies": livrees,
        "dossiers_clos": total_conclues,
        "retards_confirmes": retards,
        "reclamations_confirmees": reclamations,
        "sinistres_responsabilite_etablie": sinistres,
    }


def _calculer_score(mesures):
    livrees = mesures["livraisons_reussies"]
    dossiers = mesures["dossiers_clos"]
    if dossiers == 0:
        return None

    # Pondération publique : réussite 60, retards 20, réclamations 10,
    # sinistres avec responsabilité établie 10. Chaque malus est plafonné.
    taux_reussite = livrees / dossiers
    base_reussite = 60 * taux_reussite
    malus_retards = min(20, mesures["retards_confirmes"] * 20 / max(livrees, 1))
    malus_reclamations = min(10, mesures["reclamations_confirmees"] * 10 / max(livrees, 1))
    malus_sinistres = min(10, mesures["sinistres_responsabilite_etablie"] * 10 / max(livrees, 1))
    return max(0, min(100, round(base_reussite + 20 - malus_retards + 10 - malus_reclamations + 10 - malus_sinistres)))


def _explication_locale(score, mesures):
    return (
        f"Score {score}/100 : {mesures['livraisons_reussies']} livraison(s) réussie(s) "
        f"sur {mesures['dossiers_clos']} dossier(s) clos, avec "
        f"{mesures['retards_confirmes']} retard(s), "
        f"{mesures['reclamations_confirmees']} réclamation(s) confirmée(s) et "
        f"{mesures['sinistres_responsabilite_etablie']} sinistre(s) imputable(s)."
    )


def _expliquer_par_groq(score, mesures, cle_cache):
    if not getattr(settings, "GROQ_API_KEY", ""):
        return None
    valeur = cache.get(cle_cache)
    if valeur:
        return valeur
    # Verrou court : deux requêtes simultanées ne déclenchent pas deux appels.
    verrou = f"{cle_cache}:lock"
    if not cache.add(verrou, "1", timeout=30):
        return None
    try:
        from openai import OpenAI

        client = OpenAI(
            api_key=settings.GROQ_API_KEY,
            base_url=getattr(settings, "GROQ_BASE_URL", "https://api.groq.com/openai/v1"),
            timeout=8,
        )
        reponse = client.chat.completions.create(
            model=settings.GROQ_MODEL,
            temperature=0,
            max_tokens=100,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Explique en français un score de fiabilité. "
                        "Une seule phrase courte, factuelle, sans inventer de données."
                    ),
                },
                {
                    "role": "user",
                    "content": "Données agrégées anonymisées : "
                    + json.dumps({"score": score, **mesures}, ensure_ascii=False),
                },
            ],
        )
        texte = (reponse.choices[0].message.content or "").strip()
        if texte:
            cache.set(cle_cache, texte, EXPIRATION_EXPLICATION)
            return texte
    except Exception:
        logger.warning("Explication Groq indisponible", exc_info=True)
    finally:
        cache.delete(verrou)
    return None


def score_fiabilite(utilisateur):
    mesures = _mesures(utilisateur)
    score = _calculer_score(mesures)
    if score is None:
        return Fiabilite(None, "Données insuffisantes", mesures)

    empreinte = hashlib.sha256(json.dumps(mesures, sort_keys=True).encode()).hexdigest()[:16]
    cle_cache = f"fiabilite:explication:{utilisateur.pk}:{empreinte}"
    explication = _expliquer_par_groq(score, mesures, cle_cache) or _explication_locale(score, mesures)
    return Fiabilite(score, explication, mesures)
