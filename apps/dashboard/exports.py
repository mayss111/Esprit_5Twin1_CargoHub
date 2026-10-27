"""Exports Excel et PDF du tableau de bord."""

from html import escape
from io import BytesIO
from pathlib import Path

from django.utils import timezone
from openpyxl import Workbook
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


def excel_pilotage(kpis, series) -> bytes:
    classeur = Workbook()
    feuille = classeur.active
    feuille.title = "Pilotage"
    feuille.append(["Indicateur", "Valeur"])
    for libelle, valeur, _icone in kpis:
        feuille.append([libelle, valeur])
    feuille.append([])
    feuille.append(["Mois", "Réservations", "Encaissements (DT)"])
    for ligne in series:
        feuille.append([ligne["mois"], ligne["reservations"], ligne["encaissements"]])
    buffer = BytesIO()
    classeur.save(buffer)
    return buffer.getvalue()


def pdf_pilotage(kpis, series, remplissage=None) -> bytes:
    _polices()
    flux = BytesIO()
    document = SimpleDocTemplate(
        flux,
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=34 * mm,
        bottomMargin=18 * mm,
        title="CargoHub — tableau de bord",
        author="CargoHub",
    )
    document.build(
        _elements(kpis, series, remplissage),
        onFirstPage=lambda toile, _doc: _cadres(toile),
        onLaterPages=lambda toile, _doc: _cadres(toile),
    )
    return flux.getvalue()


def contenu_qr(kpis, remplissage) -> str:
    lignes = ["CARGOHUB", "Tableau de bord", timezone.localdate().strftime("%d/%m/%Y")]
    for libelle, valeur, _icone in kpis:
        lignes.append(f"{libelle}: {_nombre(valeur)}")
    if remplissage is not None:
        lignes.append(f"Taux de remplissage: {_nombre(remplissage)} %")
    return "\n".join(lignes)


def _elements(kpis, series, remplissage):
    blanc = _style("pilot-blanc", "DejaVu-Bold", 8, 11, colors.white)
    texte = _style("pilot-texte", "DejaVu", 9, 12, NAVY)
    petit = _style("pilot-petit", "DejaVu", 8, 11, NAVY)
    largeur = A4[0] - 32 * mm
    blocs = [_tableau_kpis(kpis, remplissage, blanc, texte, largeur), Spacer(1, 5 * mm)]
    blocs.append(Paragraph("Réservations et encaissements", _style("pilot-label", "DejaVu-Bold", 8, 11, ORANGE)))
    blocs.append(Spacer(1, 2 * mm))
    blocs.append(_tableau_series(series, blanc, petit, largeur))
    blocs.append(Spacer(1, 6 * mm))
    blocs.append(_qr(kpis, remplissage, petit, largeur))
    return blocs


def _tableau_kpis(kpis, remplissage, style_entete, style_cellule, largeur):
    lignes = [[Paragraph(escape(colonne), style_entete) for colonne in ("Indicateur", "Valeur")]]
    for libelle, valeur, _icone in kpis:
        lignes.append([Paragraph(escape(libelle), style_cellule), Paragraph(escape(_nombre(valeur)), style_cellule)])
    if remplissage is not None:
        lignes.append(
            [
                Paragraph("Taux de remplissage moyen", style_cellule),
                Paragraph(escape(f"{_nombre(remplissage)} %"), style_cellule),
            ]
        )
    tableau = Table(lignes, colWidths=[largeur * 0.72, largeur * 0.28], repeatRows=1)
    _style_tableau(tableau)
    return tableau


def _tableau_series(series, style_entete, style_cellule, largeur):
    lignes = [[Paragraph(escape(colonne), style_entete) for colonne in ("Mois", "Réservations", "Encaissements")]]
    if not series:
        lignes.append([Paragraph("Aucune donnée sur la période.", style_cellule), "", ""])
    for ligne in series:
        lignes.append(
            [
                Paragraph(escape(ligne["mois"]), style_cellule),
                Paragraph(str(ligne["reservations"]), style_cellule),
                Paragraph(escape(f"{_nombre(ligne['encaissements'])} DT"), style_cellule),
            ]
        )
    tableau = Table(lignes, colWidths=[largeur * 0.4, largeur * 0.3, largeur * 0.3], repeatRows=1)
    _style_tableau(tableau)
    return tableau


def _qr(kpis, remplissage, style_texte, largeur):
    image = Image(BytesIO(png_qr(contenu_qr(kpis, remplissage))), width=32 * mm, height=32 * mm)
    legende = Paragraph(
        "<b>Synthèse du jour</b><br/>Scannez ce code pour lire les indicateurs du tableau de bord. "
        "Il ne contient pas de données personnelles.",
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
                ("LEFTPADDING", (1, 0), (1, 0), 4),
                ("RIGHTPADDING", (1, 0), (1, 0), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return tableau


def _style_tableau(tableau):
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
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("ALIGN", (-1, 1), (-1, -1), "RIGHT"),
            ]
        )
    )


def _cadres(toile):
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
    toile.drawString(16 * mm, hauteur - 18 * mm, "Tableau de bord")
    toile.setFont("DejaVu", 9)
    toile.drawRightString(largeur - 16 * mm, hauteur - 14 * mm, timezone.localdate().strftime("%d/%m/%Y"))
    toile.setFillColor(NAVY)
    toile.rect(0, 0, largeur, 12 * mm, fill=1, stroke=0)
    toile.setFillColor(ORANGE)
    toile.rect(0, 12 * mm, largeur, 1.2 * mm, fill=1, stroke=0)
    toile.setFillColor(colors.white)
    toile.setFont("DejaVu", 8)
    toile.drawString(16 * mm, 5 * mm, "CargoHub  ·  pilotage")
    toile.drawRightString(largeur - 16 * mm, 5 * mm, "Confidentiel")
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


def _nombre(valeur) -> str:
    if isinstance(valeur, float):
        return f"{valeur:.2f}".replace(".", ",")
    return str(valeur)
