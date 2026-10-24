"""PDF du contrat de transport (reportlab), généré à la demande puis archivé une fois signé par les deux parties."""

from io import BytesIO

from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

MARINE = colors.HexColor("#0F1E3D")


def _date(valeur, format="%d/%m/%Y %H:%M"):
    return timezone.localtime(valeur).strftime(format) if valeur else "non signé"


def contrat_pdf(contrat) -> bytes:
    reservation = contrat.reservation
    expedition, trajet = reservation.expedition, reservation.trajet
    pme, transporteur = expedition.pme, trajet.transporteur
    profil_pme = getattr(pme, "profil_pme", None)

    styles = getSampleStyleSheet()
    tampon = BytesIO()
    doc = SimpleDocTemplate(
        tampon, pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm, title=f"Contrat {reservation}", author="CargoHub"
    )

    def tableau(lignes, largeurs=(5 * cm, 12 * cm), entete=False):
        t = Table(lignes, colWidths=largeurs)
        style = [("GRID", (0, 0), (-1, -1), 0.4, colors.grey), ("VALIGN", (0, 0), (-1, -1), "TOP")]
        if entete:
            style += [("BACKGROUND", (0, 0), (-1, 0), MARINE), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white)]
        t.setStyle(TableStyle(style))
        return t

    articles = [["Désignation", "Quantité", "Poids unitaire (kg)"]] + [
        [a.designation, str(a.quantite), str(a.poids_kg)] for a in expedition.articles.all()
    ]
    contenu = [
        Paragraph("CargoHub — Contrat de transport de marchandises", styles["Title"]),
        Paragraph(f"{reservation} · établi le {_date(contrat.created_at, '%d/%m/%Y')}", styles["Normal"]),
        Spacer(1, 0.5 * cm),
        Paragraph("1. Les parties", styles["Heading2"]),
        tableau(
            [
                ["Expéditeur (PME)", f"{profil_pme.raison_sociale if profil_pme else pme} — {pme.email}"],
                ["Transporteur", f"{transporteur} — {transporteur.email}"],
                ["Véhicule", f"{trajet.vehicule.get_type_display()} {trajet.vehicule.immatriculation}"],
            ]
        ),
        Paragraph("2. Le transport", styles["Heading2"]),
        tableau(
            [
                ["Enlèvement", str(expedition.adresse_depart)],
                ["Livraison", str(expedition.adresse_arrivee)],
                ["Trajet", f"{trajet.ville_depart} - {trajet.ville_arrivee}, départ le {_date(trajet.date_depart)}"],
                [
                    "Prix convenu",
                    f"{reservation.prix_convenu} TND" if reservation.prix_convenu else "selon la réservation",
                ],
            ]
        ),
        Spacer(1, 0.3 * cm),
        tableau(articles, largeurs=(9 * cm, 3 * cm, 5 * cm), entete=True),
        Paragraph("3. Conditions", styles["Heading2"]),
        Paragraph(
            "Le transporteur s’engage à acheminer la marchandise décrite ci-dessus en bon état et dans les délais. "
            "L’expéditeur garantit l’exactitude de la description et l’absence de marchandise interdite. "
            "Le paiement est effectué exclusivement via la plateforme CargoHub. "
            "Tout litige est d’abord signalé au support CargoHub.",
            styles["Normal"],
        ),
        Paragraph("4. Signatures électroniques", styles["Heading2"]),
        tableau(
            [
                ["Expéditeur (PME)", _date(contrat.signe_par_pme_le)],
                ["Transporteur", _date(contrat.signe_par_transporteur_le)],
            ]
        ),
    ]
    doc.build(contenu)
    return tampon.getvalue()
