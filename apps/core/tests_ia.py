"""
Tests de la partie IA de chaque membre, en mode « sans clé » (repli).
Ils garantissent que l'application marche même sans service d'IA.
"""

from datetime import date, timedelta
from unittest import mock

from apps.core import ai
from apps.maintenance.ai import predire_prochain_entretien
from apps.maintenance.models import Entretien
from apps.messaging.ai import moderer, repondre_support
from apps.shipments.ai import analyser_description
from apps.shipments.models import ArticleExpedie
from apps.tenders.ai import suggerer_prix
from apps.tracking.ai import analyser_sentiment


def test_ia_desactivee_sans_cle():
    assert not ai.disponible()


def test_m1_support_et_moderation():
    assert "Réserver" in repondre_support("Comment réserver un camion ?")
    assert moderer("Appelle-moi au 98 123 456")["signale"]
    assert not moderer("Bonjour, le colis est prêt")["signale"]


def test_m2_analyse_description():
    data = analyser_description("12 cartons de vêtements, environ 300 kg")
    assert data["type_marchandise"] == ArticleExpedie.Type.TEXTILE
    assert data["quantite"] == 12 and data["poids_kg"] == 300
    assert analyser_description("caisse d'explosif")["interdit"]


def test_m3_prediction_entretien(vehicule):
    for jours, km in [(0, 100_000), (30, 103_000), (60, 106_000)]:
        Entretien.objects.create(
            vehicule=vehicule, type="vidange", kilometrage=km, date=date(2026, 1, 1) + timedelta(days=jours)
        )
    resultat = predire_prochain_entretien(vehicule)
    assert resultat["methode"] == "régression linéaire"
    assert resultat["km_prevu"] == 116_000
    assert resultat["date_prevue"] == date(2026, 6, 10)  # 100 km/jour → 160 jours après le 1er janvier


def test_m4_suggestion_prix(db):
    resultat = suggerer_prix(distance_km=160, poids_kg=300)
    assert resultat["methode"] == "formule" and resultat["prix"] >= 30


def test_m5_sentiment():
    assert analyser_sentiment("Livraison rapide, merci", 5) == "POSITIF"
    assert analyser_sentiment("Colis abîmé et retard", 1) == "NEGATIF"


def test_ia_utilisee_quand_disponible(settings):
    settings.AI_API_KEY = "cle-de-test"
    with mock.patch("apps.core.ai.demander", return_value='{"sentiment": "NEUTRE"}'):
        assert analyser_sentiment("Correct", 5) == "NEUTRE"
