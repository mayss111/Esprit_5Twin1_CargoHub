"""Import Excel d'expéditions, publié par le contrôleur existant."""

import io
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from openpyxl import Workbook

from apps.shipments.models import Expedition
from apps.shipments.services.ai_checker import ArticleIA
from apps.shipments.services.import_expeditions import COLONNES

pytestmark = pytest.mark.django_db


def _ligne(**extra):
    jour = timezone.localdate() + timedelta(days=5)
    ligne = {
        "date_depart": jour.isoformat(),
        "date_arrivee": (jour + timedelta(days=1)).isoformat(),
        "description": "Cartons de textile pour un client de Sousse.",
        "depart_rue": "Zone industrielle",
        "depart_ville": "Tunis",
        "depart_gouvernorat": "Tunis",
        "depart_code_postal": "1000",
        "arrivee_rue": "Avenue de la République",
        "arrivee_ville": "Sousse",
        "arrivee_gouvernorat": "Sousse",
        "arrivee_code_postal": "4000",
        "article": "Cartons de vêtements",
        "description_article": "Textile emballé pour le transport.",
        "categorie": "TEXTILE",
        "quantite": 2,
        "poids_kg": "10",
        "volume_m3": "0.2",
        "fragile": "non",
        "valeur_declaree": "",
        "groupe": "",
    }
    ligne.update(extra)
    return ligne


def _classeur(lignes):
    classeur = Workbook()
    feuille = classeur.active
    feuille.append(list(COLONNES))
    for ligne in lignes:
        feuille.append([ligne.get(colonne, "") for colonne in COLONNES])
    sortie = io.BytesIO()
    classeur.save(sortie)
    return SimpleUploadedFile(
        "expeditions.xlsx",
        sortie.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


def _importer(client, lignes):
    return client.post(reverse("shipments:importer"), {"fichier": _classeur(lignes)})


def test_la_page_garde_le_formulaire_et_propose_lexcel(client, pme):
    client.force_login(pme)
    page = client.get(reverse("shipments:creer")).content.decode()
    assert "Publier la demande" in page
    assert "Enregistrer le brouillon" in page
    assert "Importer et publier" in page
    assert "Télécharger le modèle Excel" in page
    assert "format=xlsx" in page
    modele = client.get(reverse("shipments:importer"), {"format": "xlsx"})
    assert modele.status_code == 200
    assert modele.content[:2] == b"PK"


def test_import_publie_et_refuse_selon_les_regles(client, pme):
    client.force_login(pme)
    reponse = _importer(
        client,
        [
            _ligne(),
            _ligne(
                article="Caisse",
                description_article="Une caisse d'explosifs de chantier",
                description="Matériel de chantier à contrôler avant transport.",
            ),
        ],
    )
    assert reponse.status_code == 302
    assert reponse.url == reverse("shipments:liste")
    statuts = set(Expedition.objects.filter(pme=pme).values_list("statut", flat=True))
    assert Expedition.Statut.PUBLIEE in statuts
    assert Expedition.Statut.REFUSEE in statuts
    assert Expedition.objects.filter(pme=pme).count() == 2


def test_une_ligne_invalide_ne_cree_rien(client, pme):
    client.force_login(pme)
    passe = timezone.localdate() - timedelta(days=1)
    reponse = _importer(client, [_ligne(), _ligne(date_depart=passe.isoformat())])
    assert reponse.status_code == 200
    assert "Aucune expédition" in reponse.content.decode()
    assert Expedition.objects.filter(pme=pme).count() == 0


def test_un_groupe_reunit_plusieurs_articles(client, pme):
    client.force_login(pme)
    reponse = _importer(
        client,
        [
            _ligne(groupe="lot-1", article="Cartons"),
            _ligne(groupe="lot-1", article="Housses", description_article="Housses textiles pour vêtements."),
        ],
    )
    assert reponse.status_code == 302
    expedition = Expedition.objects.get(pme=pme)
    assert expedition.articles.count() == 2
    assert expedition.statut == Expedition.Statut.PUBLIEE


@override_settings(GEMINI_API_KEY="cle-de-test")
def test_un_risque_eleve_part_a_verifier(client, pme):
    def avis(articles, _regles):
        article = articles[0]
        return (
            [
                ArticleIA(
                    identifiant=article.pk,
                    nom=article.designation,
                    categorie_declaree=article.type_marchandise,
                    risque="ELEVE",
                    suspicion=True,
                    verification_manuelle=True,
                    motif="Pièce non identifiée",
                )
            ],
            8,
        )

    client.force_login(pme)
    with patch("apps.shipments.services.ai_checker.appeler_gemini", side_effect=avis):
        reponse = _importer(client, [_ligne(article="Pièces", description_article="Pièces détachées diverses.")])
    assert reponse.status_code == 302
    expedition = Expedition.objects.get(pme=pme)
    assert expedition.statut == Expedition.Statut.A_VERIFIER


def test_import_reserve_a_la_pme(client, transporteur):
    client.force_login(transporteur)
    assert client.get(reverse("shipments:importer"), {"format": "xlsx"}).status_code == 403
    assert _importer(client, [_ligne()]).status_code == 403
    client.logout()
    assert client.get(reverse("shipments:importer")).status_code == 302
