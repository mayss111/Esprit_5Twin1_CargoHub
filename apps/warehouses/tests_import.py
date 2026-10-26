"""Import CSV et Excel des entrepôts."""

import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from openpyxl import Workbook

from apps.warehouses.models import Entrepot
from apps.warehouses.tests import _entrepot

pytestmark = pytest.mark.django_db


def _csv(lignes, delimiteur=","):
    entete = "nom,adresse,ville,gouvernorat,capacite_max_m3,latitude,longitude,actif"
    if delimiteur == ";":
        entete = entete.replace(",", ";")
        lignes = [ligne.replace(",", ";") for ligne in lignes]
    contenu = entete + "\n" + "\n".join(lignes) + "\n"
    return SimpleUploadedFile("entrepots.csv", contenu.encode("utf-8"), content_type="text/csv")


def _xlsx(lignes):
    classeur = Workbook()
    feuille = classeur.active
    feuille.append(["nom", "adresse", "ville", "capacite_max_m3", "gouvernorat"])
    for ligne in lignes:
        feuille.append(ligne)
    sortie = io.BytesIO()
    classeur.save(sortie)
    return SimpleUploadedFile(
        "entrepots.xlsx",
        sortie.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


def test_import_csv_et_excel(client, admin_user):
    client.force_login(admin_user)
    page = client.get(reverse("bo_warehouses:importer"))
    assert page.status_code == 200
    assert "Importer des entrepôts" in page.content.decode()
    modele = client.get(reverse("bo_warehouses:importer_modele"))
    assert modele.status_code == 200
    assert b"nom" in modele.content
    excel = client.get(reverse("bo_warehouses:importer_modele"), {"format": "xlsx"})
    assert excel["Content-Disposition"].endswith('modele-entrepots.xlsx"')
    reponse = client.post(
        reverse("bo_warehouses:importer"),
        {
            "fichier": _csv(
                [
                    "Relais Nord,Rue A,Bizerte,Bizerte,12,,,oui",
                    "Relais Sud,Rue B,Sfax,Sfax,8,34.74,10.76,non",
                ]
            )
        },
    )
    assert reponse.status_code == 302
    assert Entrepot.objects.filter(nom="Relais Nord", actif=True).exists()
    sud = Entrepot.objects.get(nom="Relais Sud")
    assert sud.actif is False
    assert sud.latitude == pytest.approx(34.74)
    client.post(
        reverse("bo_warehouses:importer"),
        {"fichier": _xlsx([["Relais Centre", "Rue C", "Sousse", 15, "Sousse"]])},
    )
    cree = Entrepot.objects.get(nom="Relais Centre")
    assert cree.capacite_max_m3 == 15
    assert cree.horaire_ouverture.strftime("%H:%M") == "08:00"


def test_une_ligne_invalide_n_enregistre_rien(client, admin_user):
    client.force_login(admin_user)
    avant = Entrepot.objects.count()
    reponse = client.post(
        reverse("bo_warehouses:importer"),
        {"fichier": _csv(["Relais Bon,Rue A,Tunis,Tunis,10,,,oui", "Relais Mauvais,Rue B,Tunis,Inconnu,10,,,oui"])},
    )
    assert reponse.status_code == 200
    assert "gouvernorat" in reponse.content.decode()
    assert Entrepot.objects.count() == avant
    _entrepot(nom="Relais Déjà", ville="Monastir")
    doublon = client.post(
        reverse("bo_warehouses:importer"),
        {"fichier": _csv(["Relais Déjà,Rue A,Monastir,Monastir,10,,,oui"])},
    )
    assert "déjà ce nom" in doublon.content.decode()
    assert Entrepot.objects.filter(nom="Relais Déjà").count() == 1


def test_fichier_refuse_et_acces_pme(client, admin_user, pme):
    client.force_login(admin_user)
    mauvais = SimpleUploadedFile("entrepots.txt", b"nom\n", content_type="text/plain")
    refuse = client.post(reverse("bo_warehouses:importer"), {"fichier": mauvais})
    assert refuse.status_code == 200
    assert "csv" in refuse.content.decode().lower()
    client.force_login(pme)
    assert client.get(reverse("bo_warehouses:importer")).status_code == 403
    refuse_pme = client.post(
        reverse("bo_warehouses:importer"),
        {"fichier": _csv(["A,Rue,Tunis,Tunis,5,,,oui"])},
    )
    assert refuse_pme.status_code == 403
    assert not Entrepot.objects.filter(nom="A").exists()
