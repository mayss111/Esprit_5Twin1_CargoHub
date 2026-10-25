"""Logique métier du module Flotte — Membre 3 : compatibilité, conformité, CO₂ et certificat vert.

Utilisée par les vues Django, l'API REST et les tâches Celery. La compatibilité trajet / expédition
et les notifications sont celles du module Réservations (M4) : on les réutilise au lieu de les dupliquer.
"""

import datetime
import logging
from decimal import Decimal

from django.urls import reverse
from django.utils import timezone

from apps.bookings import services as reservations
from apps.bookings.tasks import notifier as notifier_tache

from .models import FacteurEmission, Trajet, Vehicule

logger = logging.getLogger("cargohub.fleet")

# Distance moyenne (km) d'un trajet entre deux villes tunisiennes — sert quand la distance
# exacte n'est pas connue.
DISTANCE_MOYENNE_KM = 150


def trajets_compatibles(expedition):
    """Trajets ouverts qui peuvent accueillir l'expédition, du meilleur au moins bon (règle du module M4)."""
    return [t for t, _score in reservations.trajets_compatibles(expedition) if t.est_compatible(expedition)]


def notifier(destinataire, titre, message, lien=""):
    """Notification dans l'application + email, envoyée par la tâche Celery partagée avec M4."""
    notifier_tache.delay(destinataire.pk, titre, message, lien)


def verifier_conformite_flotte():
    """Recalcule le statut de chaque véhicule et notifie le transporteur si bloqué.

    Retourne (bloqués, réactivés).
    """
    bloques, reactives = 0, 0
    for vehicule in Vehicule.objects.select_related("transporteur"):
        avant = vehicule.statut
        apres = vehicule.recalculer_conformite()
        if apres == Vehicule.Statut.NON_CONFORME and avant != Vehicule.Statut.NON_CONFORME:
            bloques += 1
            notifier(
                vehicule.transporteur,
                "Véhicule non conforme",
                f"{vehicule} a été bloqué : {vehicule.motif_non_conformite}",
                reverse("fleet:vehicules"),
            )
            logger.info("Véhicule %s bloqué (non conforme)", vehicule.immatriculation)
        elif apres != Vehicule.Statut.NON_CONFORME and avant == Vehicule.Statut.NON_CONFORME:
            reactives += 1
            notifier(
                vehicule.transporteur,
                "Véhicule de nouveau conforme",
                f"{vehicule} peut de nouveau publier des trajets.",
                reverse("fleet:vehicules"),
            )
    return bloques, reactives


def calculer_co2_trajet(trajet, charge_kg):
    """emissions = distance × facteur(type véhicule) × (charge / capacité)."""
    facteur = FacteurEmission.pour(trajet.vehicule.type)
    distance = trajet.distance_km or DISTANCE_MOYENNE_KM
    capacite = trajet.capacite_totale_kg or trajet.vehicule.capacite_kg
    taux_charge = min(max(Decimal(str(charge_kg)) / Decimal(capacite), Decimal("0")), Decimal("1"))
    return float(Decimal(str(distance)) * facteur * taux_charge)


def mettre_a_jour_co2_trajet(trajet):
    """Calcule et stocke le CO₂ du trajet à partir de la charge réellement réservée."""
    trajet.co2_kg = calculer_co2_trajet(trajet, trajet.capacite_reservee_kg)
    trajet.save(update_fields=["co2_kg"])
    return trajet.co2_kg


def bilan_co2(transporteur, periode_debut=None, periode_fin=None, vehicule=None):
    """Bilan cumulé d'un transporteur (ou d'un seul de ses véhicules) : trajets, CO₂ total, points éco (pour M5)."""
    trajets = Trajet.objects.filter(transporteur=transporteur, statut=Trajet.Statut.TERMINE)
    if vehicule is not None:
        trajets = trajets.filter(vehicule=vehicule)
    if periode_debut:
        debut = timezone.make_aware(datetime.datetime.combine(periode_debut, datetime.time.min))
        trajets = trajets.filter(date_depart__gte=debut)
    if periode_fin:
        fin = timezone.make_aware(datetime.datetime.combine(periode_fin, datetime.time.max))
        trajets = trajets.filter(date_depart__lte=fin)
    co2_total = sum((t.co2_kg or 0) for t in trajets)
    # 1 point éco tous les 100 kg de CO₂ évité par le partage ( envoyé au module Fidélité M5)
    points_eco = int(co2_total // 100)
    return {"nb_trajets": trajets.count(), "co2_total_kg": round(co2_total, 2), "points_eco": points_eco}


# --------------------------------------------------------------------- PDF
def generer_certificat_vert(transporteur, periode_debut, periode_fin, vehicule=None):
    """Génère le certificat vert PDF (reportlab) du transporteur, ou d'un seul véhicule. Renvoie (octets, bilan)."""
    from io import BytesIO

    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.pdfgen import canvas

    bilan = bilan_co2(transporteur, periode_debut, periode_fin, vehicule=vehicule)
    tampon = BytesIO()
    pdf = canvas.Canvas(tampon, pagesize=A4)
    largeur, hauteur = A4

    pdf.setFillColorRGB(0.106, 0.165, 0.29)  # bleu marine #1B2A4A
    pdf.rect(0, hauteur - 4 * cm, largeur, 4 * cm, fill=1, stroke=0)
    pdf.setFillColorRGB(0.96, 0.65, 0.14)  # orange #F5A623
    pdf.setFont("Helvetica-Bold", 26)
    pdf.drawString(2 * cm, hauteur - 2.6 * cm, "CargoHub — Certificat vert")
    pdf.setFillColorRGB(1, 1, 1)
    pdf.setFont("Helvetica", 12)
    pdf.drawString(2 * cm, hauteur - 3.5 * cm, f"Période : du {periode_debut:%d/%m/%Y} au {periode_fin:%d/%m/%Y}")

    pdf.setFillColorRGB(0, 0, 0)
    pdf.setFont("Helvetica", 14)
    y = hauteur - 7 * cm
    for ligne in (
        f"Transporteur : {transporteur.get_full_name() or transporteur.email}",
        f"Véhicule : {vehicule}" if vehicule else "Véhicule : toute la flotte",
        f"Trajets terminés : {bilan['nb_trajets']}",
        f"CO2 émis (charge partagée) : {bilan['co2_total_kg']} kg",
        f"Points éco gagnés : {bilan['points_eco']}",
    ):
        pdf.drawString(2 * cm, y, ligne)
        y -= 1.2 * cm

    pdf.setFont("Helvetica-Oblique", 9)
    pdf.drawString(2 * cm, 2 * cm, f"Généré le {timezone.now():%d/%m/%Y à %H:%M} — CargoHub, covoiturage de fret")
    pdf.showPage()
    pdf.save()
    logger.info("Certificat vert généré pour %s (%s → %s)", transporteur.email, periode_debut, periode_fin)
    return tampon.getvalue(), bilan
