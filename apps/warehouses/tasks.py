"""Tâches d'entrepôt. Celery Beat clôture les réservations. Le worker classe les entrepôts."""

import logging
from datetime import datetime

from celery import shared_task
from django.db import transaction
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from apps.core.resultat_ia import ecrire
from apps.warehouses.models import CreneauDepot
from apps.warehouses.services.alerts import prevenir
from apps.warehouses.services.capacity import STATUTS_ACTIFS, fin_reservation
from apps.warehouses.services.recommander import recommander, vers_json

logger = logging.getLogger(__name__)

MESSAGE_ECHEC = "La recherche n'a pas abouti. Réessayez."


@shared_task
def suivre_depots():
    cloturer_reservations()


@shared_task
def calculer_recommandation_entrepots(user_id, expedition_id, jour_iso, jeton):
    """Classe les entrepôts hors de la requête HTTP. Le site lit le résultat ensuite."""
    from django.contrib.auth import get_user_model

    cle = f"reco:{jeton}"
    utilisateur = get_user_model().objects.filter(pk=user_id).first()
    if utilisateur is None:
        ecrire(cle, {"statut": "ERREUR", "user_id": user_id, "erreur": MESSAGE_ECHEC})
        return
    jour = None
    if jour_iso:
        jour = datetime.strptime(jour_iso, "%Y-%m-%d").date()
    try:
        resultat = vers_json(recommander(utilisateur, expedition_id, jour))
    except Exception:
        logger.exception("Recommandation d'entrepôt en échec pour l'utilisateur %s", user_id)
        ecrire(cle, {"statut": "ERREUR", "user_id": user_id, "erreur": MESSAGE_ECHEC})
        return
    ecrire(cle, {"statut": "PRET", "user_id": user_id, "resultat": resultat})


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
