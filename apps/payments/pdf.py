"""Facture PDF CargoHub : mise en page et QR code de vérification."""

from html import escape
from io import BytesIO
from pathlib import Path

from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from apps.shipments.services.bon_pdf import png_qr

NAVY = colors.HexColor("#0F1E3D")
ORANGE = colors.HexColor("#E87722")
CREAM = colors.HexColor("#F7F5F2")
PALE = colors.HexColor("#EEF2F8")
LINE = colors.HexColor("#D5DBE6")
_POLICES = False


def rendre_pdf(facture) -> bytes:
    _polices()
    paiement = facture.paiement
    flux = BytesIO()
    document = SimpleDocTemplate(
        flux,
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=34 * mm,
        bottomMargin=18 * mm,
        title=facture.numero,
        author="CargoHub",
    )
    document.build(
        _elements(facture),
        onFirstPage=lambda toile, _doc: _cadres(toile, facture, paiement),
        onLaterPages=lambda toile, _doc: _cadres(toile, facture, paiement),
    )
    return flux.getvalue()


def contenu_qr(facture) -> str:
    paiement = facture.paiement
    return "\n".join(
        [
            "CARGOHUB",
            f"Facture {facture.numero}",
            f"Montant {paiement.montant} DT",
            f"Reservation #{paiement.reservation_id}",
            f"Statut {paiement.statut}",
        ]
    )


def _elements(facture):
    paiement = facture.paiement
    reservation = paiement.reservation
    expedition = reservation.expedition
    trajet = reservation.trajet
    label = _style("label", "DejaVu-Bold", 8, 11, ORANGE)
    texte = _style("texte", "DejaVu", 9, 12, NAVY)
    petit = _style("petit", "DejaVu", 8, 11, NAVY)
    blanc = _style("blanc", "DejaVu-Bold", 8, 11, colors.white)
    montant = _style("montant", "DejaVu-Bold", 12, 15, colors.white)
    largeur = A4[0] - 32 * mm

    client = _carte(
        "Client",
        [expedition.pme.get_full_name() or "PME", expedition.pme.email],
        label,
        texte,
        largeur * 0.48,
    )
    transport = _carte(
        "Transport",
        [
            f"{trajet.ville_depart} → {trajet.ville_arrivee}",
            trajet.transporteur.get_full_name() or "Transporteur",
            trajet.transporteur.email,
        ],
        label,
        texte,
        largeur * 0.48,
    )
    haut = Table([[client, transport]], colWidths=[largeur * 0.5, largeur * 0.5])
    haut.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (0, 0), 4),
                ("LEFTPADDING", (1, 0), (1, 0), 4),
                ("RIGHTPADDING", (1, 0), (1, 0), 0),
                ("BACKGROUND", (0, 0), (-1, -1), colors.white),
            ]
        )
    )
    return [
        haut,
        Spacer(1, 4 * mm),
        _lignes(facture, reservation, blanc, petit, largeur),
        Spacer(1, 3 * mm),
        _total(paiement, montant, largeur),
        Spacer(1, 6 * mm),
        _qr(facture, texte, largeur),
    ]


def _lignes(facture, reservation, style_entete, style_cellule, largeur):
    paiement = facture.paiement
    prix = reservation.prix_convenu or paiement.montant
    lignes = [[Paragraph(escape(colonne), style_entete) for colonne in ("Prestation", "Détail", "Montant")]]
    lignes.append(
        [
            Paragraph("Transport de fret", style_cellule),
            Paragraph(escape(f"Réservation #{reservation.pk} · {facture.numero}"), style_cellule),
            Paragraph(_dt(prix), style_cellule),
        ]
    )
    if paiement.code_promo and prix != paiement.montant:
        remise = prix - paiement.montant
        lignes.append(
            [
                Paragraph("Remise", style_cellule),
                Paragraph(escape(f"Code {paiement.code_promo}"), style_cellule),
                Paragraph(f"− {_dt(remise)}", style_cellule),
            ]
        )
    commission = getattr(paiement, "commission", None)
    if commission is not None:
        lignes.append(
            [
                Paragraph("Commission plateforme", style_cellule),
                Paragraph(escape(f"{commission.taux * 100:.0f} %"), style_cellule),
                Paragraph(_dt(commission.montant_commission), style_cellule),
            ]
        )
    tableau = Table(lignes, colWidths=[largeur * 0.34, largeur * 0.42, largeur * 0.24], repeatRows=1)
    tableau.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PALE]),
                ("GRID", (0, 0), (-1, -1), 0.3, LINE),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("ALIGN", (2, 1), (2, -1), "RIGHT"),
            ]
        )
    )
    return tableau


def _total(paiement, style_montant, largeur):
    libelle = Paragraph("Montant à payer", _style("total-lib", "DejaVu", 9, 12, colors.white))
    valeur = Paragraph(_dt(paiement.montant), style_montant)
    tableau = Table([[libelle, valeur]], colWidths=[largeur * 0.62, largeur * 0.38])
    tableau.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), NAVY),
                ("TEXTCOLOR", (0, 0), (-1, -1), colors.white),
                ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    return tableau


def _qr(facture, style_texte, largeur):
    image = Image(BytesIO(png_qr(contenu_qr(facture))), width=32 * mm, height=32 * mm)
    legende = Paragraph(
        "<b>Vérification</b><br/>Scannez ce code pour lire le numéro de facture, "
        "le montant et le statut. Il ne contient ni coordonnées bancaires ni adresse.",
        style_texte,
    )
    tableau = Table([[image, legende]], colWidths=[38 * mm, largeur - 38 * mm])
    tableau.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("BACKGROUND", (0, 0), (-1, -1), CREAM),
                ("BOX", (0, 0), (-1, -1), 1.2, ORANGE),
                ("LEFTPADDING", (0, 0), (0, 0), 4),
                ("RIGHTPADDING", (0, 0), (0, 0), 2),
                ("LEFTPADDING", (1, 0), (1, 0), 4),
                ("RIGHTPADDING", (1, 0), (1, 0), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return tableau


def _carte(titre, lignes, style_titre, style_texte, largeur):
    contenu = [Paragraph(escape(titre), style_titre)]
    contenu.extend(Paragraph(escape(ligne), style_texte) for ligne in lignes if ligne)
    tableau = Table([[contenu]], colWidths=[largeur])
    tableau.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), PALE),
                ("BOX", (0, 0), (-1, -1), 0.4, LINE),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    return tableau


def _cadres(toile, facture, paiement):
    largeur, hauteur = A4
    toile.saveState()
    toile.setFillColor(NAVY)
    toile.rect(0, hauteur - 26 * mm, largeur, 26 * mm, fill=1, stroke=0)
    toile.setFillColor(ORANGE)
    toile.rect(0, hauteur - 28 * mm, largeur, 2 * mm, fill=1, stroke=0)
    toile.setFillColor(colors.white)
    toile.setFont("DejaVu-Bold", 16)
    toile.drawString(16 * mm, hauteur - 12 * mm, "CARGOHUB")
    toile.setFont("DejaVu", 8)
    toile.drawString(16 * mm, hauteur - 18 * mm, "Facture de transport")
    toile.setFont("DejaVu-Bold", 11)
    toile.drawRightString(largeur - 16 * mm, hauteur - 12 * mm, facture.numero)
    toile.setFont("DejaVu", 8)
    date = f"{timezone.localtime(facture.created_at):%d/%m/%Y}" if facture.created_at else ""
    toile.drawRightString(largeur - 16 * mm, hauteur - 18 * mm, f"{paiement.get_statut_display()}  ·  {date}")
    toile.setFillColor(NAVY)
    toile.rect(0, 0, largeur, 12 * mm, fill=1, stroke=0)
    toile.setFillColor(ORANGE)
    toile.rect(0, 12 * mm, largeur, 1.2 * mm, fill=1, stroke=0)
    toile.setFillColor(colors.white)
    toile.setFont("DejaVu", 8)
    toile.drawString(16 * mm, 5 * mm, "CargoHub  ·  facture électronique")
    toile.drawRightString(largeur - 16 * mm, 5 * mm, facture.numero)
    toile.restoreState()


def _polices():
    global _POLICES
    if _POLICES:
        return
    dossier = Path(__file__).resolve().parent.parent / "shipments" / "fonts"
    regular = dossier / "DejaVuSans.ttf"
    bold = dossier / "DejaVuSans-Bold.ttf"
    if not regular.is_file():
        regular = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
        bold = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
    pdfmetrics.registerFont(TTFont("DejaVu", str(regular)))
    pdfmetrics.registerFont(TTFont("DejaVu-Bold", str(bold)))
    _POLICES = True


def _style(nom, police, taille, interligne, couleur):
    return ParagraphStyle(nom, fontName=police, fontSize=taille, leading=interligne, textColor=couleur)


def _dt(valeur) -> str:
    return f"{valeur:.2f}".replace(".", ",") + " DT"
