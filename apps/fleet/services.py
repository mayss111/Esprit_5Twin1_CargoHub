"""Services du module Flotte — compatibilité, conformité, CO₂ et certificat vert.

Utilisés à la fois par les vues Django, l'API REST et les tâches Celery.
"""

import datetime
import logging
from decimal import Decimal

from django.utils import timezone

from .models import FacteurEmission, Trajet, Vehicule

logger = logging.getLogger("cargohub.fleet")

# Aire urbaine moyenne (km²) d'une ville tunisienne — sert quand la distance
# exacte n'est pas connue. L'OSRM (M2) peut la remplacer plus tard.
DISTANCE_MOYENNE_KM = 150


def trajets_compatibles(expedition):
    """Tous les trajets publiés qui peuvent accueillir l'expédition (utilisé par M4)."""
    return [
        t
        for t in Trajet.objects.filter(statut=Trajet.Statut.PUBLIE).select_related("vehicule")
        if t.est_compatible(expedition)
    ]


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
                lien="/flotte/vehicules/",
            )
            logger.info("Véhicule %s bloqué (non conforme)", vehicule.immatriculation)
        elif apres != Vehicule.Statut.NON_CONFORME and avant == Vehicule.Statut.NON_CONFORME:
            reactives += 1
            notifier(
                vehicule.transporteur,
                "Véhicule de nouveau conforme",
                f"{vehicule} peut de nouveau publier des trajets.",
                lien="/flotte/vehicules/",
            )
    return bloques, reactives


def notifier(destinataire, titre, message, lien=""):
    """Notification in-app partagée avec le module Réservations (M4)."""
    from apps.bookings.models import Notification

    return Notification.objects.create(destinataire=destinataire, titre=titre, message=message, lien=lien)


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


def bilan_co2(transporteur, periode_debut=None, periode_fin=None):
    """Bilan cumulé d'un transporteur : trajets, CO₂ total, points éco (pour M5)."""
    trajets = Trajet.objects.filter(transporteur=transporteur, statut=Trajet.Statut.TERMINE)
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
def generer_certificat_vert(transporteur, periode_debut, periode_fin):
    """Génère le certificat vert PDF (reportlab) et renvoie les octets du fichier."""
    from io import BytesIO

    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.pdfgen import canvas

    bilan = bilan_co2(transporteur, periode_debut, periode_fin)
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
    pdf.drawString(2 * cm, hauteur - 3.5 * cm, f"Période : {periode_debut:%d/%m/%Y} → {periode_fin:%d/%m/%Y}")

    pdf.setFillColorRGB(0, 0, 0)
    pdf.setFont("Helvetica", 14)
    y = hauteur - 7 * cm
    for ligne in (
        f"Transporteur : {transporteur.get_full_name() or transporteur.email}",
        f"Trajets terminés : {bilan['nb_trajets']}",
        f"CO₂ émis (charge partagée) : {bilan['co2_total_kg']} kg",
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
