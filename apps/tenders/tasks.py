from celery import shared_task
from django.utils import timezone

from .models import AppelOffre


@shared_task
def cloturer_appels_offres():
    """M4 — ferme les appels d'offres dont la date de clôture est passée (attribution : à compléter)."""
    return AppelOffre.objects.filter(statut=AppelOffre.Statut.OUVERT, date_cloture__lt=timezone.now()).update(
        statut=AppelOffre.Statut.CLOTURE
    )
