"""Vérification des marchandises et assistant de saisie, hors de la requête HTTP."""

import logging

from celery import shared_task

from apps.core.resultat_ia import ecrire
from apps.shipments.models import Expedition
from apps.shipments.services.ai_checker import VerificationIndisponible, appliquer_verification
from apps.shipments.services.ai_form_assistant import (
    AssistantIndisponible,
    AssistantInvalide,
    analyser_description,
)

logger = logging.getLogger(__name__)


@shared_task
def verifier_expedition(expedition_id):
    """Gemini et les règles CargoHub décident du statut après l'enregistrement."""
    expedition = Expedition.objects.filter(pk=expedition_id).first()
    if expedition is None:
        return
    try:
        appliquer_verification(expedition)
    except VerificationIndisponible as exc:
        expedition.statut = Expedition.Statut.BROUILLON
        expedition.motif_decision = str(exc)
        expedition.empreinte_verification = ""
        expedition.save(update_fields=["statut", "motif_decision", "empreinte_verification", "updated_at"])
    except Exception:
        logger.exception("Vérification en échec pour l'expédition %s", expedition_id)
    ecrire(f"verif:{expedition_id}", {"statut": "PRET"})


@shared_task
def preparer_assistant(description, user_id, jeton):
    """Propose les champs. N'enregistre aucune expédition."""
    cle = f"assistant:{jeton}"
    try:
        resultat = analyser_description(description, user_id)
    except AssistantInvalide as exc:
        ecrire(cle, {"statut": "ERREUR", "user_id": user_id, "code": 400, "erreur": str(exc)})
        return
    except AssistantIndisponible as exc:
        ecrire(cle, {"statut": "ERREUR", "user_id": user_id, "code": 503, "erreur": str(exc)})
        return
    except Exception:
        logger.exception("Assistant de saisie en échec pour l'utilisateur %s", user_id)
        ecrire(
            cle,
            {
                "statut": "ERREUR",
                "user_id": user_id,
                "code": 503,
                "erreur": "L'assistant est momentanément indisponible. Saisissez le formulaire manuellement.",
            },
        )
        return
    ecrire(cle, {"statut": "PRET", "user_id": user_id, "resultat": resultat})
