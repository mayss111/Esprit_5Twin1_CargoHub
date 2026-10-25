import logging

from celery import shared_task
from django.utils import timezone

from apps.core import ai

from .ai import recommander_offre
from .models import AppelOffre

logger = logging.getLogger(__name__)


@shared_task
def cloturer_appels_offres():
    """M4 — ferme les appels d'offres dont la date de clôture est passée (attribution : à compléter)."""
    return AppelOffre.objects.filter(statut=AppelOffre.Statut.OUVERT, date_cloture__lt=timezone.now()).update(
        statut=AppelOffre.Statut.CLOTURE
    )


@shared_task
def calculer_recommandation(appel_id: int):
    """M4 — « Aide au choix » : l'appel au LLM prend 1 à 3 s, il est fait en arrière-plan et enregistré sur l'appel."""
    appel = AppelOffre.objects.filter(pk=appel_id).first()
    if appel is None:
        return
    # Seule une analyse encore attendue est enregistrée : si une offre est arrivée entre-temps, le résultat est périmé.
    en_attente = AppelOffre.objects.filter(pk=appel_id, recommandation_statut=AppelOffre.Recommandation.EN_COURS)
    try:
        resultat, duree_ms = ai.mesurer(recommander_offre, appel)
    except Exception:
        logger.exception("Aide au choix en échec pour l’appel %s", appel_id)
        en_attente.update(recommandation_statut=AppelOffre.Recommandation.ERREUR, recommandation_ia=None)
        return
    en_attente.update(
        recommandation_ia=resultat,
        recommandation_statut=AppelOffre.Recommandation.PRETE,
        recommandation_duree_ms=duree_ms,
    )
