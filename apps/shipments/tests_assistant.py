import json
from datetime import timedelta
from pathlib import Path

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.shipments.forms import SaisieExpedition
from apps.shipments.models import Expedition
from apps.shipments.services.ai_form_assistant import (
    AssistantIndisponible,
    analyser_description,
    generer_json,
)
from apps.shipments.tests import _article, _donnees

MOIS = (
    "janvier",
    "février",
    "mars",
    "avril",
    "mai",
    "juin",
    "juillet",
    "août",
    "septembre",
    "octobre",
    "novembre",
    "décembre",
)


def _jour():
    return timezone.localdate() + timedelta(days=21)


def _texte(jour):
    mois = MOIS[jour.month - 1]
    return (
        f"Je veux envoyer 5 cartons d'ordinateurs portables et 3 écrans de Tunis à Sousse "
        f"le {jour.day} {mois} {jour.year}. Le poids total est de 80 kg. Les écrans sont fragiles."
    )


def _reponse(jour):
    return json.dumps(
        {
            "adresse_depart": {"ligne": "12 rue inventée", "ville": "Tunis", "code_postal": "9999"},
            "adresse_arrivee": {"ville": "Sousse", "ligne": "Sousse"},
            "date_depart": jour.isoformat(),
            "date_arrivee": "2020-01-01",
            "articles": [
                {
                    "nom": "Ordinateurs portables",
                    "quantite": 5,
                    "unite": "cartons",
                    "categorie_proposee": "Informatique",
                    "fragile": True,
                    "poids_kg": 40,
                    "volume_m3": 1.5,
                },
                {
                    "nom": "Écrans",
                    "quantite": 3,
                    "unite": "pièces",
                    "categorie_proposee": "Électronique",
                    "fragile": False,
                    "description": "Dalle inventée par le modèle",
                },
                {"nom": "Souris inventée", "quantite": 1, "categorie_proposee": "Electronique"},
            ],
            "poids_total_declare": 80,
        },
        ensure_ascii=False,
    )


def _poster(client, texte):
    return client.post(
        reverse("shipments:assistant"),
        data=json.dumps({"description": texte}),
        content_type="application/json",
    )


def test_extraction_sans_invention(client, pme, monkeypatch):
    jour = _jour()
    texte = _texte(jour)
    monkeypatch.setattr(
        "apps.shipments.services.ai_form_assistant.generer_json",
        lambda _description: (_reponse(jour), 123),
    )
    client.force_login(pme)
    avant = Expedition.objects.count()
    reponse = _poster(client, texte)
    assert reponse.status_code == 200
    data = reponse.json()
    assert Expedition.objects.count() == avant
    assert "statut" not in data
    assert data["duree_ms"] == 123
    assert data["champs"]["depart-ville"] == "Tunis"
    assert data["champs"]["depart-gouvernorat"] == "Tunis"
    assert data["champs"]["arrivee-ville"] == "Sousse"
    assert data["champs"]["arrivee-gouvernorat"] == "Sousse"
    assert data["champs"]["generale-date_souhaitee"] == jour.isoformat()
    assert data["champs"]["generale-description"] == texte
    assert "depart-ligne" not in data["champs"]
    assert "depart-code_postal" not in data["champs"]
    assert "generale-date_arrivee" not in data["champs"]
    assert "arrivee-ligne" not in data["champs"]
    assert [article["designation"] for article in data["articles"]] == ["Ordinateurs portables", "Écrans"]
    ordinateurs, ecrans = data["articles"]
    assert ordinateurs["quantite"] == 5
    assert ordinateurs["type_marchandise"] == "ELECTRONIQUE"
    assert ordinateurs["fragile"] is None
    assert ordinateurs["poids_kg"] is None
    assert ordinateurs["volume_m3"] is None
    assert ordinateurs["unite"] == "cartons"
    assert ecrans["quantite"] == 3
    assert ecrans["fragile"] is True
    assert ecrans["poids_kg"] is None
    assert ecrans["description"] is None
    assert ecrans["unite"] is None
    assert data["poids_total_declare"] == 80
    manquantes = " ".join(data["informations_manquantes"]).lower()
    assert "volume" in manquantes
    assert "adresse exacte" in manquantes
    assert any("rapprochée" in message for message in data["avertissements"])
    assert any("80 kg" in message for message in data["avertissements"])


def test_categorie_inconnue_et_date_passee(pme, monkeypatch):
    texte = "Envoyer 2 cages d'oiseaux de Tunis vers Sfax le 1 janvier 2020."
    brut = json.dumps(
        {
            "adresse_depart": {"ville": "Tunis"},
            "adresse_arrivee": {"ville": "Sfax"},
            "date_depart": "2020-01-01",
            "articles": [{"nom": "Oiseaux", "quantite": None, "categorie_proposee": "Animaux"}],
        }
    )
    monkeypatch.setattr(
        "apps.shipments.services.ai_form_assistant.generer_json",
        lambda _description: (brut, 40),
    )
    data = analyser_description(texte, pme.pk)
    assert data["articles"][0]["type_marchandise"] is None
    assert data["articles"][0]["quantite"] is None
    assert "generale-date_souhaitee" not in data["champs"]
    assert any("ne correspond" in message for message in data["avertissements"])
    assert any("passée" in message for message in data["avertissements"])
    assert any("Quantité" in message for message in data["informations_manquantes"])


def test_json_incorrect_et_api_indisponible(client, pme, monkeypatch):
    client.force_login(pme)
    monkeypatch.setattr(
        "apps.shipments.services.ai_form_assistant.generer_json",
        lambda _description: ("{pas du json", 10),
    )
    reponse = _poster(client, "Cinq cartons de tissus de Tunis à Sousse la semaine prochaine.")
    assert reponse.status_code == 503
    assert "champs" not in reponse.json()
    assert Expedition.objects.filter(pme=pme).count() == 0

    def _panne(_description):
        raise AssistantIndisponible("L'assistant est momentanément indisponible. Saisissez le formulaire manuellement.")

    monkeypatch.setattr("apps.shipments.services.ai_form_assistant.generer_json", _panne)
    reponse = _poster(client, "Cinq cartons de tissus de Tunis à Sousse la semaine prochaine.")
    assert reponse.status_code == 503
    assert "GEMINI_API_KEY" not in reponse.content.decode()


def test_sans_cle_api_aucun_appel(settings):
    settings.GEMINI_API_KEY = ""
    with pytest.raises(AssistantIndisponible):
        generer_json("Description assez longue pour un appel.")


def test_appel_identique_utilise_le_cache(pme, monkeypatch):
    appels = {"n": 0}

    def _faux(_description):
        appels["n"] += 1
        return ('{"articles":[]}', 15)

    monkeypatch.setattr("apps.shipments.services.ai_form_assistant.generer_json", _faux)
    texte = "Transport de tissus de Tunis vers Sousse sans autre précision utile."
    premier = analyser_description(texte, pme.pk)
    second = analyser_description(texte, pme.pk)
    assert appels["n"] == 1
    assert premier["depuis_cache"] is False
    assert second["depuis_cache"] is True
    assert second["duree_ms"] == 15


def test_description_trop_courte(client, pme):
    client.force_login(pme)
    reponse = _poster(client, "court")
    assert reponse.status_code == 400


def test_page_nouvelle_expedition_affiche_lassistant(client, pme, expedition):
    client.force_login(pme)
    page = client.get(reverse("shipments:creer")).content.decode()
    assert "Créer mon expédition avec l'IA" in page
    assert "Remplir automatiquement avec l'IA" in page
    assert "assistant.js" in page
    modification = client.get(reverse("shipments:modifier", args=[expedition.pk])).content.decode()
    assert "Créer mon expédition avec l'IA" not in modification
    script = Path("static/shipments/js/assistant.js").read_text(encoding="utf-8")
    assert "form.submit" not in script
    assert "id_articles-" in script
    assert "id_" in script
    assert "valeur_declaree" in script
    assert "nombreChamp" in script
    assert 'replace(",", ".")' in script
    assert "ajouter.click" in script


def _texte_mesures():
    return (
        "Article 1 : 5 cartons de livres, poids unitaire 10 kg, volume unitaire 0,08 m³, "
        "valeur déclarée unitaire 100 DT, non fragile. "
        "Article 2 : 3 écrans d'ordinateur, poids unitaire 7 kg, volume unitaire 0,12 m³, "
        "valeur déclarée unitaire 550 DT, fragile."
    )


def test_mesures_unitaires_virgule_et_fragile(pme, monkeypatch):
    brut = json.dumps(
        {
            "articles": [
                {
                    "nom": "Cartons de livres",
                    "quantite": 5,
                    "poids_kg": "10",
                    "volume_m3": "0,08",
                    "valeur_declaree": 100,
                    "fragile": False,
                    "categorie_proposee": "GENERAL",
                },
                {
                    "nom": "Écrans d'ordinateur",
                    "quantite": 3,
                    "poids_kg": 7,
                    "volume_m3": "0.12",
                    "valeur_declaree": "550",
                    "fragile": True,
                    "categorie_proposee": "ELECTRONIQUE",
                },
            ]
        },
        ensure_ascii=False,
    )
    monkeypatch.setattr(
        "apps.shipments.services.ai_form_assistant.generer_json",
        lambda _description: (brut, 30),
    )
    data = analyser_description(_texte_mesures(), pme.pk)
    livres, ecrans = data["articles"]
    assert livres["quantite"] == 5
    assert livres["poids_kg"] == 10
    assert livres["volume_m3"] == "0.08"
    assert livres["valeur_declaree"] == 100
    assert livres["fragile"] is False
    assert ecrans["quantite"] == 3
    assert ecrans["poids_kg"] == 7
    assert ecrans["volume_m3"] == "0.12"
    assert ecrans["valeur_declaree"] == 550
    assert ecrans["fragile"] is True
    assert data["totaux"] == {"poids_kg": 71, "volume_m3": "0.76", "valeur_declaree": 2150}
    assert data["poids_total_declare"] is None
    assert not any("réparti" in message for message in data["avertissements"])


def test_mesures_extraites_quand_gemini_les_omet(pme, monkeypatch):
    brut = json.dumps(
        {
            "articles": [
                {"nom": "Cartons de livres", "quantite": 5},
                {"nom": "Écrans d'ordinateur", "quantite": 3},
            ]
        },
        ensure_ascii=False,
    )
    monkeypatch.setattr(
        "apps.shipments.services.ai_form_assistant.generer_json",
        lambda _description: (brut, 12),
    )
    data = analyser_description(_texte_mesures(), pme.pk)
    livres, ecrans = data["articles"]
    assert livres["poids_kg"] == 10
    assert livres["volume_m3"] == "0.08"
    assert livres["valeur_declaree"] == 100
    assert livres["fragile"] is False
    assert ecrans["poids_kg"] == 7
    assert ecrans["volume_m3"] == "0.12"
    assert ecrans["valeur_declaree"] == 550
    assert ecrans["fragile"] is True
    assert data["totaux"]["poids_kg"] == 71


def test_fragile_non_precise_reste_vide_et_total_non_reparti(pme, monkeypatch):
    texte = "Envoyer 4 caisses de livres et 2 cartons de vaisselle de Tunis à Sfax. Le poids total est de 30 kg."
    brut = json.dumps(
        {
            "articles": [
                {
                    "nom": "Caisses de livres",
                    "quantite": 4,
                    "poids_kg": 12,
                    "volume_m3": 1,
                    "valeur_declaree": 80,
                    "fragile": False,
                },
                {"nom": "Cartons de vaisselle", "quantite": 2, "fragile": True},
            ],
            "poids_total_declare": 30,
        },
        ensure_ascii=False,
    )
    monkeypatch.setattr(
        "apps.shipments.services.ai_form_assistant.generer_json",
        lambda _description: (brut, 8),
    )
    data = analyser_description(texte, pme.pk)
    livres, vaisselle = data["articles"]
    assert livres["poids_kg"] is None
    assert livres["volume_m3"] is None
    assert livres["valeur_declaree"] is None
    assert livres["fragile"] is None
    assert vaisselle["fragile"] is None
    assert vaisselle["poids_kg"] is None
    assert data["poids_total_declare"] == 30
    assert data["totaux"]["poids_kg"] is None
    assert any("n'a pas été réparti" in message for message in data["avertissements"])


def test_prompt_demande_les_mesures_unitaires():
    from apps.shipments.services.ai_form_assistant import _consigne

    consigne = _consigne("Exemple de description assez longue.")
    assert "valeur_declaree" in consigne
    assert "false" in consigne
    assert "0,08" in consigne
    assert "ne répartis jamais un total" in consigne.lower() or "Ne répartis jamais un total" in consigne


def test_assistant_ne_contourne_pas_le_controle(client, pme, monkeypatch):
    monkeypatch.setattr(
        "apps.shipments.services.ai_form_assistant.generer_json",
        lambda _description: ('{"articles":[{"nom":"explosifs","quantite":1}]}', 5),
    )
    client.force_login(pme)
    reponse = _poster(client, "Je dois déclarer une caisse d'explosifs pour le chantier de Tunis.")
    assert reponse.status_code == 200
    assert Expedition.objects.filter(pme=pme).count() == 0
    jour = timezone.localdate() + timedelta(days=3)
    saisie = SaisieExpedition(
        _donnees(jour, [_article(designation="Caisse", description="Une caisse d'explosifs de chantier")]),
        pme=pme,
        publier=True,
    )
    assert saisie.is_valid(), saisie.generale.errors
    expedition = saisie.save()
    assert expedition.statut == Expedition.Statut.REFUSEE
