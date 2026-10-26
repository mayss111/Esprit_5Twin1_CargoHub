"""Logique métier du suivi : positions, preuve de livraison, incidents et avis."""

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone

from apps.bookings.models import Reservation
from apps.bookings.services import ReservationImpossible, changer_statut
from apps.core.roles import est_admin

from .ai import analyser_sentiment
from .models import Avis, Incident, PreuveLivraison, SuiviPosition

STATUTS_OUVERTS = (Reservation.Statut.ACCEPTEE, Reservation.Statut.EN_TRANSIT)
STATUTS_SUIVI = (*STATUTS_OUVERTS, Reservation.Statut.LIVREE)


class SuiviImpossible(Exception):
    pass


def reservations_de(user):
    qs = Reservation.objects.select_related("expedition__pme", "trajet__transporteur", "trajet__vehicule")
    if est_admin(user):
        return qs
    return qs.filter(Q(expedition__pme=user) | Q(trajet__transporteur=user))


def get_reservation(user, pk):
    return get_object_or_404(reservations_de(user), pk=pk, statut__in=STATUTS_SUIVI)


def est_transporteur_de(user, reservation) -> bool:
    return reservation.trajet.transporteur_id == user.pk


def est_pme_de(user, reservation) -> bool:
    return reservation.expedition.pme_id == user.pk


def est_partie(user, reservation) -> bool:
    return est_admin(user) or est_pme_de(user, reservation) or est_transporteur_de(user, reservation)


def _vers_transit(reservation, user):
    if reservation.statut == Reservation.Statut.ACCEPTEE:
        try:
            changer_statut(reservation, Reservation.Statut.EN_TRANSIT, par=user, motif="Départ signalé")
        except ReservationImpossible as exc:
            raise SuiviImpossible(str(exc)) from exc
        reservation.refresh_from_db()


@transaction.atomic
def ajouter_position(reservation, user, latitude, longitude) -> SuiviPosition:
    if not (est_transporteur_de(user, reservation) or est_admin(user)):
        raise SuiviImpossible("Seul le transporteur peut signaler une position.")
    if reservation.statut not in STATUTS_OUVERTS:
        raise SuiviImpossible("Le suivi n’est ouvert que pour une réservation acceptée ou en transit.")
    _vers_transit(reservation, user)
    position = SuiviPosition(reservation=reservation, latitude=latitude, longitude=longitude)
    try:
        position.full_clean()
    except ValidationError as exc:
        raise SuiviImpossible(" ".join(exc.messages)) from exc
    position.save()
    return position


@transaction.atomic
def deposer_preuve(reservation, user, photo=None) -> PreuveLivraison:
    if not (est_transporteur_de(user, reservation) or est_admin(user)):
        raise SuiviImpossible("Seul le transporteur peut déposer la preuve de livraison.")
    if reservation.statut not in STATUTS_OUVERTS:
        raise SuiviImpossible("La preuve se dépose pendant le transport.")
    preuve = PreuveLivraison.objects.filter(reservation=reservation).first()
    if preuve and preuve.confirmee_le:
        raise SuiviImpossible("Cette livraison est déjà confirmée.")
    _vers_transit(reservation, user)
    if preuve is None:
        from secrets import randbelow

        preuve = PreuveLivraison(reservation=reservation, code_otp=f"{randbelow(1_000_000):06d}")
    if photo:
        preuve.photo = photo
    preuve.save()
    return preuve


@transaction.atomic
def confirmer_livraison(reservation, user, code: str) -> PreuveLivraison:
    if not (est_pme_de(user, reservation) or est_admin(user)):
        raise SuiviImpossible("Seule la PME destinataire peut confirmer la livraison.")
    preuve = PreuveLivraison.objects.filter(reservation=reservation).first()
    if preuve is None:
        raise SuiviImpossible("Le transporteur n’a pas encore communiqué de code.")
    if preuve.confirmee_le:
        raise SuiviImpossible("Cette livraison est déjà confirmée.")
    if (code or "").strip() != preuve.code_otp:
        raise SuiviImpossible("Le code ne correspond pas.")
    if reservation.statut not in STATUTS_OUVERTS:
        raise SuiviImpossible("Cette réservation ne peut plus être livrée.")
    _vers_transit(reservation, user)
    try:
        changer_statut(reservation, Reservation.Statut.LIVREE, par=user, motif="Code de livraison confirmé")
    except ReservationImpossible as exc:
        raise SuiviImpossible(str(exc)) from exc
    preuve.confirmee_le = timezone.now()
    preuve.save(update_fields=["confirmee_le", "updated_at"])
    from apps.payments.services import PaiementImpossible, assurer_paiement

    try:
        assurer_paiement(reservation)
    except PaiementImpossible:
        pass
    return preuve


def declarer_incident(reservation, user, type_incident, description) -> Incident:
    if not est_partie(user, reservation):
        raise SuiviImpossible("Vous ne participez pas à cette livraison.")
    if reservation.statut not in STATUTS_SUIVI:
        raise SuiviImpossible("Un incident se déclare sur une livraison en cours ou terminée.")
    incident = Incident(
        reservation=reservation,
        declare_par=user,
        type=type_incident,
        description=description.strip(),
    )
    try:
        incident.full_clean()
    except ValidationError as exc:
        raise SuiviImpossible(" ".join(exc.messages)) from exc
    incident.save()
    return incident


def laisser_avis(reservation, user, note: int, commentaire: str) -> Avis:
    if reservation.statut != Reservation.Statut.LIVREE:
        raise SuiviImpossible("L’avis se dépose une fois la livraison confirmée.")
    if est_pme_de(user, reservation):
        cible = reservation.trajet.transporteur
    elif est_transporteur_de(user, reservation):
        cible = reservation.expedition.pme
    else:
        raise SuiviImpossible("Vous ne participez pas à cette livraison.")
    avis, _cree = Avis.objects.update_or_create(
        reservation=reservation,
        auteur=user,
        defaults={
            "cible": cible,
            "note": note,
            "commentaire": (commentaire or "").strip(),
            "sentiment": analyser_sentiment(commentaire, note),
        },
    )
    from .tasks import calculer_resume

    calculer_resume.delay(reservation.trajet.transporteur_id)
    return avis
