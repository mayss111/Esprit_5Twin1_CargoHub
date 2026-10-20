from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from .models import Trajet


@shared_task
def generer_trajets_recurrents():
    """M3 — recopie chaque trajet récurrent sur la semaine suivante s'il n'existe pas encore."""
    maintenant = timezone.now()
    crees = 0
    for trajet in Trajet.objects.filter(
        recurrent=True, date_depart__range=(maintenant, maintenant + timedelta(days=7))
    ):
        prochaine = trajet.date_depart + timedelta(days=7)
        existe = Trajet.objects.filter(
            transporteur=trajet.transporteur,
            vehicule=trajet.vehicule,
            ville_depart=trajet.ville_depart,
            ville_arrivee=trajet.ville_arrivee,
            date_depart=prochaine,
        ).exists()
        if not existe:
            Trajet.objects.create(
                transporteur=trajet.transporteur,
                vehicule=trajet.vehicule,
                ville_depart=trajet.ville_depart,
                ville_arrivee=trajet.ville_arrivee,
                date_depart=prochaine,
                capacite_dispo_kg=trajet.vehicule.capacite_kg,
                capacite_dispo_m3=trajet.vehicule.capacite_m3,
                prix_indicatif=trajet.prix_indicatif,
                distance_km=trajet.distance_km,
                recurrent=True,
            )
            crees += 1
    return crees
