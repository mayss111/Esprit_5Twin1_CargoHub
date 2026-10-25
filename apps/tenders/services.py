"""Logique métier des appels d'offres — Membre 4."""

from django.db import transaction

from apps.bookings.models import Reservation
from apps.bookings.services import ReservationImpossible, changer_statut, reserver
from apps.bookings.tasks import notifier

from .models import AppelOffre, Offre


@transaction.atomic
def retenir_offre(offre: Offre, par) -> Reservation:
    """
    La PME choisit une offre : elle est RETENUE, les autres REJETEES, l'appel ATTRIBUE,
    et la réservation est créée puis acceptée (le transporteur s'est engagé en faisant son offre).
    Tout se fait dans une seule transaction : si le camion n'a plus de place, rien n'est modifié.
    """
    appel = AppelOffre.objects.select_for_update().get(pk=offre.appel_id)
    offre = Offre.objects.select_related("trajet").get(pk=offre.pk)
    if appel.statut != AppelOffre.Statut.OUVERT:
        raise ReservationImpossible("Cet appel d’offres n’est plus ouvert.")
    if offre.statut != Offre.Statut.PROPOSEE:
        raise ReservationImpossible("Cette offre n’est plus disponible.")
    if offre.trajet is None:
        raise ReservationImpossible("Cette offre n’indique plus de trajet : demandez au transporteur de la modifier.")

    appel.offres.exclude(pk=offre.pk).update(statut=Offre.Statut.REJETEE)
    offre.statut = Offre.Statut.RETENUE
    offre.save(update_fields=["statut", "updated_at"])
    appel.statut = AppelOffre.Statut.ATTRIBUE
    appel.save(update_fields=["statut", "updated_at"])

    reservation = reserver(appel.expedition, offre.trajet, prix=offre.prix)
    reservation = changer_statut(reservation, Reservation.Statut.ACCEPTEE, par=par)  # renvoie l'objet à jour

    transaction.on_commit(
        lambda: notifier.delay(
            offre.transporteur_id,
            "Votre offre a été retenue",
            f"Votre offre de {offre.prix} DT pour {appel} a été retenue : réservation #{reservation.pk} acceptée.",
        )
    )
    return reservation
