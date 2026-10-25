"""Tâches asynchrones du module Flotte (Celery) — M3.

Remarque : la liste des entretiens vient du module « Entretien & conformité »
(apps.maintenance, membre 3 également).
"""

from datetime import timedelta

from celery import shared_task
from django.core.mail import send_mail
from django.utils import timezone

from apps.maintenance.models import Entretien

from . import services
from .models import JOURS_ALERTE_EXPIRATION, DocumentVehicule, Trajet, Vehicule


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
                capacite_totale_kg=trajet.vehicule.capacite_kg,
                capacite_totale_m3=trajet.vehicule.capacite_m3,
                prix_indicatif=trajet.prix_indicatif,
                distance_km=trajet.distance_km,
                recurrent=True,
            )
            crees += 1
    return crees


@shared_task
def verifier_conformite_flotte():
    """Tâche quotidienne (Celery Beat) : recalcule les statuts, bloque les véhicules non conformes."""
    bloques, reactives = services.verifier_conformite_flotte()
    return {"bloques": bloques, "reactives": reactives}


@shared_task
def notifier_alerte_documents():
    """Alerte par email + notification in-app : documents qui expirent sous 30 jours."""
    limite = timezone.localdate() + timedelta(days=JOURS_ALERTE_EXPIRATION)
    alertes = 0
    for doc in DocumentVehicule.objects.filter(
        date_expiration__lte=limite, date_expiration__gte=timezone.localdate()
    ).select_related("vehicule__transporteur"):
        services.notifier(
            doc.vehicule.transporteur,
            "Document bientôt expiré",
            f"{doc.get_type_display()} du véhicule {doc.vehicule.immatriculation} "
            f"expire le {doc.date_expiration:%d/%m/%Y}.",
            lien="/flotte/vehicules/",
        )
        send_mail(
            subject="CargoHub — document de véhicule bientôt expiré",
            message=f"Le document {doc.get_type_display()} du véhicule {doc.vehicule.immatriculation} "
            f"expire le {doc.date_expiration:%d/%m/%Y}. Pensez à le renouveler.",
            from_email=None,
            recipient_list=[doc.vehicule.transporteur.email],
            fail_silently=True,
        )
        alertes += 1
    return alertes


@shared_task
def notifier_alerte_entretien():
    """Rappel des entretiens dont la prochaine échéance arrive (module Entretien)."""
    limite = timezone.localdate() + timedelta(days=7)
    rappels = 0
    for entretien in Entretien.objects.filter(prochaine_echeance__lte=limite).select_related("vehicule__transporteur"):
        services.notifier(
            entretien.vehicule.transporteur,
            "Entretien à prévoir",
            f"{entretien.vehicule} : entretien « {entretien.type} » "
            f"à prévoir avant le {entretien.prochaine_echeance:%d/%m/%Y}.",
            lien="/entretien/",
        )
        rappels += 1
    return rappels


@shared_task
def generer_certificat_vert(vehicule_id=None, transporteur_id=None, periode_debut=None, periode_fin=None):
    """Génère un certificat vert (PDF). Le résultat est renvoyé au module Fidélité (M5)."""
    from apps.accounts.models import Utilisateur

    if not transporteur_id:
        transporteur_id = Vehicule.objects.get(pk=vehicule_id).transporteur_id
    transporteur = Utilisateur.objects.get(pk=transporteur_id)
    periode_fin = periode_fin or timezone.localdate()
    periode_debut = periode_debut or periode_fin - timedelta(days=365)
    contenu, bilan = services.generer_certificat_vert(transporteur, periode_debut, periode_fin)
    return {"octets": len(contenu), **bilan}
