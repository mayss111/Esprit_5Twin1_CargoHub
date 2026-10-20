from celery import shared_task
from django.utils import timezone

from apps.fleet.models import Vehicule


@shared_task
def verifier_conformite():
    """M3 — bloque les véhicules dont le dernier contrôle technique est expiré ou défavorable."""
    aujourd_hui = timezone.localdate()
    bloques = 0
    for vehicule in Vehicule.objects.filter(conforme=True):
        dernier = vehicule.controles.order_by("-date_controle").first()
        if dernier and (dernier.date_expiration < aujourd_hui or not dernier.favorable):
            vehicule.conforme = False
            vehicule.save(update_fields=["conforme"])
            bloques += 1
    return bloques
