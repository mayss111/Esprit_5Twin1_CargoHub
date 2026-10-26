"""Exports Excel et PDF du tableau de bord."""

from io import BytesIO

from openpyxl import Workbook
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas


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


def pdf_pilotage(kpis, series) -> bytes:
    buffer = BytesIO()
    page = canvas.Canvas(buffer, pagesize=A4)
    page.setTitle("CargoHub — tableau de bord")
    page.setFont("Helvetica-Bold", 16)
    page.drawString(50, 800, "CargoHub — tableau de bord")
    page.setFont("Helvetica", 11)
    y = 770
    for libelle, valeur, _icone in kpis:
        page.drawString(50, y, f"{libelle} : {valeur}")
        y -= 18
    y -= 10
    page.setFont("Helvetica-Bold", 12)
    page.drawString(50, y, "Réservations et encaissements")
    page.setFont("Helvetica", 11)
    for ligne in series:
        y -= 18
        page.drawString(50, y, f"{ligne['mois']} — {ligne['reservations']} réservation(s), {ligne['encaissements']} DT")
    page.showPage()
    page.save()
    return buffer.getvalue()
