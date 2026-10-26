"""Bon d'expédition PDF. Le QR Code est le lien de la référence publique.

ReportLab est utilisé à la place de WeasyPrint : le paquet est déjà installé
et ne demande pas Cairo ni Pango. Les accents passent par les polices DejaVu
vendues avec l'application (repli : fonts-dejavu-core dans l'image Docker).
Le logo du site est un SVG, que ReportLab ne dessine pas : l'en-tête reprend
le nom CargoHub en bleu marine et orange.
"""

from html import escape
from io import BytesIO
from pathlib import Path

import qrcode
from django.urls import reverse
from django.utils import timezone
from qrcode.constants import ERROR_CORRECT_M
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

NAVY = colors.HexColor("#0F1E3D")
ORANGE = colors.HexColor("#E87722")
CREAM = colors.HexColor("#F7F5F2")
PALE = colors.HexColor("#EEF2F8")
_POLICES = False


def jeton_bon(expedition):
    """Référence déjà imprimée sur le bon. Le QR Code n'ajoute pas d'autre secret."""
    return expedition.reference


def lire_jeton(jeton):
    from apps.shipments.models import Expedition

    reference = (jeton or "").strip()
    if not reference:
        return None
    return Expedition.objects.filter(reference=reference).values_list("pk", flat=True).first()


def url_verification(request, expedition):
    chemin = reverse("shipments:verifier", kwargs={"jeton": jeton_bon(expedition)})
    return request.build_absolute_uri(chemin)


def png_qr(url):
    code = qrcode.QRCode(error_correction=ERROR_CORRECT_M, box_size=6, border=2)
    code.add_data(url)
    code.make(fit=True)
    image = code.make_image(fill_color="#0F1E3D", back_color="white")
    flux = BytesIO()
    image.save(flux, format="PNG")
    return flux.getvalue()


def generer_pdf(expedition, url):
    """Produit le PDF sans enregistrer ni dupliquer l'expédition."""
    _polices()
    flux = BytesIO()
    document = SimpleDocTemplate(
        flux,
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=32 * mm,
        bottomMargin=16 * mm,
        title=expedition.reference,
        author="CargoHub",
        pageCompression=0,
        invariant=1,
    )
    document.build(
        elements_bon(expedition, url),
        onFirstPage=lambda toile, _doc: _entete(toile, expedition),
        onLaterPages=lambda toile, _doc: _entete(toile, expedition),
    )
    return flux.getvalue()


def textes_bon(expedition, url):
    textes = []
    for element in elements_bon(expedition, url):
        _ajouter_texte(element, textes)
    return textes


def elements_bon(expedition, url):
    _polices()
    titre = _style("titre", "DejaVu-Bold", 13, 16, NAVY)
    label = _style("label", "DejaVu-Bold", 8, 11, ORANGE)
    texte = _style("texte", "DejaVu", 8, 11, NAVY)
    petit = _style("petit", "DejaVu", 7.5, 10, NAVY)
    blanc = _style("blanc", "DejaVu-Bold", 7.5, 10, colors.white)
    articles = list(expedition.articles.all())
    blocs = [Paragraph("BON D'EXPÉDITION", titre), Spacer(1, 2 * mm)]
    blocs.extend(
        _bloc(
            "Référence",
            [
                expedition.reference,
                f"Créée le {_date_heure(expedition.created_at)}",
                f"Départ prévu le {_date(expedition.date_souhaitee)}",
                f"Arrivée prévue le {_date(expedition.date_arrivee)}",
                f"Statut : {expedition.get_statut_display()}",
            ],
            label,
            texte,
        )
    )
    blocs.extend(_bloc("PME", _lignes_pme(expedition), label, texte))
    blocs.extend(
        _bloc(
            "Transport",
            [
                f"Départ : {_adresse(expedition.adresse_depart)}",
                f"Arrivée : {_adresse(expedition.adresse_arrivee)}",
            ],
            label,
            texte,
        )
    )
    if expedition.description:
        blocs.extend(_bloc("Description", [expedition.description], label, texte))
    blocs.extend(
        [
            Spacer(1, 3 * mm),
            Paragraph("Articles", label),
            Spacer(1, 1 * mm),
            _tableau(articles, blanc, petit),
            Spacer(1, 2 * mm),
            Paragraph(
                "Poids total : "
                f"<b>{_nombre(expedition.poids_total_kg)} kg</b>"
                " · Volume total : "
                f"<b>{_nombre(expedition.volume_total_m3)} m³</b>"
                f" · Nombre d'articles : <b>{len(articles)}</b>"
                f" · Quantité totale : <b>{sum(article.quantite for article in articles)}</b>",
                texte,
            ),
            Spacer(1, 4 * mm),
            _qr(url, texte),
        ]
    )
    return blocs


def _polices():
    global _POLICES
    if _POLICES:
        return
    dossier = Path(__file__).resolve().parent.parent / "fonts"
    regular = dossier / "DejaVuSans.ttf"
    bold = dossier / "DejaVuSans-Bold.ttf"
    if not regular.is_file():
        regular = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
        bold = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
    pdfmetrics.registerFont(TTFont("DejaVu", str(regular)))
    pdfmetrics.registerFont(TTFont("DejaVu-Bold", str(bold)))
    _POLICES = True


def _style(nom, police, taille, interligne, couleur):
    return ParagraphStyle(
        nom,
        fontName=police,
        fontSize=taille,
        leading=interligne,
        textColor=couleur,
        spaceAfter=0,
    )


def _bloc(titre, lignes, style_titre, style_texte):
    contenu = [Paragraph(escape(titre), style_titre)]
    contenu.extend(Paragraph(escape(ligne), style_texte) for ligne in lignes if ligne)
    return contenu


def _lignes_pme(expedition):
    utilisateur = expedition.pme
    profil = getattr(utilisateur, "profil_pme", None)
    raison = getattr(profil, "raison_sociale", "") or utilisateur.get_full_name() or utilisateur.email
    lignes = [raison, utilisateur.email]
    if utilisateur.telephone:
        lignes.append(utilisateur.telephone)
    matricule = getattr(profil, "matricule_fiscal", "")
    if matricule:
        lignes.append(f"Matricule fiscal : {matricule}")
    adresse = ", ".join(part for part in (getattr(profil, "adresse", ""), getattr(profil, "ville", "")) if part)
    if adresse:
        lignes.append(adresse)
    return lignes


def _adresse(adresse):
    morceaux = [adresse.ligne, adresse.ville]
    if adresse.code_postal:
        morceaux.append(adresse.code_postal)
    if adresse.gouvernorat:
        morceaux.append(adresse.gouvernorat)
    return ", ".join(morceaux)


def _tableau(articles, style_entete, style_cellule):
    entetes = ["Article", "Description", "Catégorie", "Qté", "Poids", "Volume", "Fragile"]
    lignes = [[Paragraph(escape(colonne), style_entete) for colonne in entetes]]
    if not articles:
        lignes.append([Paragraph("Aucun article enregistré.", style_cellule), "", "", "", "", "", ""])
    for article in articles:
        lignes.append(
            [
                Paragraph(escape(article.designation), style_cellule),
                Paragraph(escape(article.description or "—"), style_cellule),
                Paragraph(escape(article.get_type_marchandise_display()), style_cellule),
                Paragraph(str(article.quantite), style_cellule),
                Paragraph(f"{_nombre(article.poids_kg)} kg", style_cellule),
                Paragraph(f"{_nombre(article.volume_m3)} m³", style_cellule),
                Paragraph("Oui" if article.fragile else "Non", style_cellule),
            ]
        )
    largeur = A4[0] - 32 * mm
    parts = [0.18, 0.24, 0.16, 0.08, 0.12, 0.12, 0.10]
    tableau = Table(lignes, colWidths=[largeur * part for part in parts], repeatRows=1)
    tableau.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("BACKGROUND", (0, 1), (-1, -1), CREAM),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PALE]),
                ("FONTNAME", (0, 0), (-1, -1), "DejaVu"),
                ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#D5DBE6")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 3),
                ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    return tableau


def _qr(url, style_texte):
    image = Image(BytesIO(png_qr(url)), width=32 * mm, height=32 * mm)
    legende = Paragraph(
        "QR Code de cette expédition. Il ouvre la page de sa référence "
        "et ne contient ni adresse, ni coordonnées, ni description des marchandises.",
        style_texte,
    )
    tableau = Table([[image, legende]], colWidths=[36 * mm, A4[0] - 68 * mm])
    tableau.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("BACKGROUND", (0, 0), (-1, -1), colors.white),
                ("BOX", (0, 0), (-1, -1), 1, ORANGE),
                ("LEFTPADDING", (1, 0), (1, 0), 4),
            ]
        )
    )
    return tableau


def _entete(toile, expedition):
    largeur, hauteur = A4
    toile.saveState()
    toile.setFillColor(NAVY)
    toile.rect(0, hauteur - 22 * mm, largeur, 22 * mm, fill=1, stroke=0)
    toile.setFillColor(ORANGE)
    toile.rect(0, hauteur - 24 * mm, largeur, 2 * mm, fill=1, stroke=0)
    toile.setFillColor(colors.white)
    toile.setFont("DejaVu-Bold", 14)
    toile.drawString(16 * mm, hauteur - 12 * mm, "CARGOHUB")
    toile.setFont("DejaVu", 8)
    toile.drawString(16 * mm, hauteur - 17 * mm, "Covoiturage de fret")
    toile.setFont("Helvetica", 9)
    toile.drawRightString(largeur - 16 * mm, hauteur - 14 * mm, expedition.reference)
    toile.setFillColor(NAVY)
    toile.rect(0, 0, largeur, 10 * mm, fill=1, stroke=0)
    toile.setFillColor(colors.white)
    toile.setFont("Helvetica", 8)
    toile.drawString(16 * mm, 4 * mm, f"CargoHub  |  {expedition.reference}")
    toile.restoreState()


def _date(jour):
    return f"{jour:%d/%m/%Y}"


def _date_heure(moment):
    return f"{timezone.localtime(moment):%d/%m/%Y %H:%M}"


def _nombre(valeur):
    texte = format(valeur, "f")
    if "." in texte:
        texte = texte.rstrip("0").rstrip(".")
    return texte or "0"


def _ajouter_texte(element, textes):
    if isinstance(element, Paragraph):
        textes.append(element.getPlainText())
    elif isinstance(element, Table):
        for ligne in element._cellvalues:
            for cellule in ligne:
                _ajouter_texte(cellule, textes)
    elif isinstance(element, (list, tuple)):
        for sous in element:
            _ajouter_texte(sous, textes)
