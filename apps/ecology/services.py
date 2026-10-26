"""Calcul de l'empreinte carbone évitée par les réservations livrées."""

from decimal import Decimal

from apps.fleet.models import FacteurEmission
from apps.fleet.services import DISTANCE_MOYENNE_KM

from .models import EmpreinteCarbone


def enregistrer_empreinte_reservation(reservation):
    """Enregistre les émissions partagées et le scénario dédié d'une livraison."""
    trajet = reservation.trajet
    facteur = FacteurEmission.pour(trajet.vehicule.type)
    distance = Decimal(str(trajet.distance_km or DISTANCE_MOYENNE_KM))
    capacite = Decimal(str(trajet.capacite_totale_kg or trajet.vehicule.capacite_kg))
    poids = Decimal(str(reservation.expedition.poids_total_kg))
    taux_charge = min(max(poids / capacite, Decimal("0")), Decimal("1"))
    co2_dedie = distance * facteur
    co2_partage = co2_dedie * taux_charge

    empreinte, _ = EmpreinteCarbone.objects.update_or_create(
        reservation=reservation,
        defaults={
            "distance_km": float(distance),
            "co2_partage_kg": round(float(co2_partage), 2),
            "co2_dedie_kg": round(float(co2_dedie), 2),
        },
    )
    return empreinte
