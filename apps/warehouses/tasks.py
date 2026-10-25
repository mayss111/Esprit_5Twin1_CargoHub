"""Clôture des réservations échues. Exécutée par Celery Beat, jamais par un thread de vue."""

from celery import shared_task
from django.db import transaction
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from apps.warehouses.models import CreneauDepot
from apps.warehouses.services.alerts import prevenir
from apps.warehouses.services.capacity import STATUTS_ACTIFS, fin_reservation


@shared_task
def suivre_depots():
    cloturer_reservations()


def cloturer_reservations(maintenant=None):
    """Passe à Terminé les réservations dont la fin est atteinte et libère leur volume."""
    maintenant = maintenant or timezone.now()
    candidats = (
        CreneauDepot.objects.filter(statut__in=STATUTS_ACTIFS)
        .filter(Q(fin_stockage_prevue__lte=maintenant) | Q(fin_stockage_prevue__isnull=True, fin__lte=maintenant))
        .values_list("pk", flat=True)
    )
    for identifiant in candidats:
        termine = None
        with transaction.atomic():
            creneau = (
                CreneauDepot.objects.select_for_update()
                .select_related("entrepot", "expedition__pme")
                .filter(pk=identifiant, statut__in=STATUTS_ACTIFS)
                .first()
            )
            if creneau is None or fin_reservation(creneau) > maintenant:
                continue
            creneau.statut = CreneauDepot.Statut.TERMINE
            creneau.save(update_fields=["statut", "updated_at"])
            termine = creneau
        if termine is not None:
            prevenir(
                termine.expedition.pme,
                "Réservation terminée",
                (
                    f"La réservation {termine.reference} est terminée. "
                    f"L'espace de {termine.volume_reserve or 0} m³ est libéré."
                ),
                reverse("warehouses:depot", args=[termine.pk]),
            )
