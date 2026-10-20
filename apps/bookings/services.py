"""
Logique métier du cœur de CargoHub — Membre 4.

Les vues appellent ces fonctions ; elles ne modifient jamais une réservation
« à la main ». Ça garantit que la capacité et l'historique restent justes.
"""

from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.fleet.models import Trajet

from .models import HistoriqueStatut, Reservation
from .tasks import notifier


class ReservationImpossible(Exception):
    pass


def score_compatibilite(expedition, trajet) -> int:
    """Score de 0 à 100 : même itinéraire, date proche, place suffisante (à affiner par M4)."""
    score = 0
    depart, arrivee = expedition.adresse_depart.ville.lower(), expedition.adresse_arrivee.ville.lower()
    villes = (
        [trajet.ville_depart.lower()] + [e.ville.lower() for e in trajet.etapes.all()] + [trajet.ville_arrivee.lower()]
    )
    if depart in villes and arrivee in villes and villes.index(depart) < villes.index(arrivee):
        score += 50
    ecart_jours = abs((trajet.date_depart.date() - expedition.date_souhaitee).days)
    score += max(0, 30 - ecart_jours * 10)
    if trajet.capacite_dispo_kg >= expedition.poids_total_kg and trajet.capacite_dispo_m3 >= expedition.volume_total_m3:
        score += 20
    return score


def trajets_compatibles(expedition, score_minimum=60):
    """Trajets ouverts autour de la date souhaitée, classés du meilleur au moins bon."""
    date = expedition.date_souhaitee
    candidats = Trajet.objects.filter(
        statut=Trajet.Statut.OUVERT,
        vehicule__conforme=True,
        date_depart__date__range=(date - timedelta(days=2), date + timedelta(days=2)),
    ).prefetch_related("etapes")
    resultats = [(t, score_compatibilite(expedition, t)) for t in candidats]
    return sorted([r for r in resultats if r[1] >= score_minimum], key=lambda r: r[1], reverse=True)


def reserver(expedition, trajet, prix=None) -> Reservation:
    """Crée une réservation EN_ATTENTE et prévient le transporteur."""
    reservation = Reservation.objects.create(
        expedition=expedition,
        trajet=trajet,
        prix_convenu=prix or trajet.prix_indicatif,
        score_matching=score_compatibilite(expedition, trajet),
    )
    notifier.delay(
        trajet.transporteur_id,
        "Nouvelle demande de réservation",
        f"{expedition} demande une place sur votre trajet {trajet}.",
    )
    return reservation


@transaction.atomic
def changer_statut(reservation: Reservation, nouveau: str, par=None) -> Reservation:
    """
    Fait passer une réservation d'un statut à un autre en respectant le diagramme d'états.
    À l'acceptation, la place du trajet est retirée de façon sûre (verrou sur la ligne),
    pour que deux PME ne puissent jamais réserver la même place en même temps.
    """
    reservation = Reservation.objects.select_for_update().get(pk=reservation.pk)
    if not reservation.peut_passer_a(nouveau):
        raise ReservationImpossible(f"Impossible de passer de {reservation.statut} à {nouveau}")

    trajet = Trajet.objects.select_for_update().get(pk=reservation.trajet_id)
    poids = Decimal(reservation.expedition.poids_total_kg)
    volume = Decimal(reservation.expedition.volume_total_m3)

    if nouveau == Reservation.Statut.ACCEPTEE:
        if trajet.capacite_dispo_kg < poids or trajet.capacite_dispo_m3 < volume:
            raise ReservationImpossible("Plus assez de place dans ce camion")
        trajet.capacite_dispo_kg -= poids
        trajet.capacite_dispo_m3 -= volume
        trajet.save(update_fields=["capacite_dispo_kg", "capacite_dispo_m3"])
    elif nouveau == Reservation.Statut.ANNULEE and reservation.statut == Reservation.Statut.ACCEPTEE:
        trajet.capacite_dispo_kg += poids
        trajet.capacite_dispo_m3 += volume
        trajet.save(update_fields=["capacite_dispo_kg", "capacite_dispo_m3"])

    HistoriqueStatut.objects.create(reservation=reservation, ancien=reservation.statut, nouveau=nouveau, par=par)
    reservation.statut = nouveau
    reservation.save(update_fields=["statut", "updated_at"])

    transaction.on_commit(
        lambda: notifier.delay(
            reservation.expedition.pme_id,
            f"Réservation #{reservation.pk} : {reservation.get_statut_display()}",
            f"Le statut de votre réservation est maintenant « {reservation.get_statut_display()} » "
            f"({timezone.localtime():%d/%m/%Y %H:%M}).",
        )
    )
    return reservation
