"""Recommandation d'entrepôts : capacité, horaires, repli et permissions."""

from datetime import time, timedelta
from decimal import Decimal

import pytest
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Utilisateur
from apps.core.roles import Role
from apps.shipments.models import Adresse, ArticleExpedie, Expedition
from apps.warehouses.models import CreneauDepot
from apps.warehouses.services import recommander as service
from apps.warehouses.tests import _entrepot

pytestmark = pytest.mark.django_db


class _Modele:
    def encode(self, textes, normalize_embeddings=True):
        vecteurs = []
        for texte in textes:
            plie = texte.casefold()
            if plie.startswith("expédition") or "nord" in plie:
                vecteurs.append([1.0, 0.0])
            else:
                vecteurs.append([0.0, 1.0])
        return vecteurs


def _expedition(pme, volume="2", ville_depart="Tunis", latitude=36.8, longitude=10.18):
    expedition = Expedition.objects.create(
        pme=pme,
        adresse_depart=Adresse.objects.create(
            ligne="Rue de départ", ville=ville_depart, latitude=latitude, longitude=longitude
        ),
        adresse_arrivee=Adresse.objects.create(ligne="Rue d'arrivée", ville="Sfax"),
        date_souhaitee=timezone.localdate() + timedelta(days=4),
        date_arrivee=timezone.localdate() + timedelta(days=5),
        statut=Expedition.Statut.PUBLIEE,
        description="Expédition de test pour le recommandeur d'entrepôts.",
    )
    ArticleExpedie.objects.create(
        expedition=expedition,
        designation="Cartons",
        quantite=1,
        poids_kg=Decimal("8"),
        volume_m3=Decimal(volume),
    )
    return expedition


def _occuper(entrepot, pme, volume):
    expedition = _expedition(pme, volume=volume, ville_depart="Autre")
    debut = timezone.now() + timedelta(days=1)
    return CreneauDepot.objects.create(
        entrepot=entrepot,
        expedition=expedition,
        debut=debut,
        fin=debut + timedelta(hours=2),
        fin_stockage_prevue=debut + timedelta(days=6),
        volume_reserve=Decimal(volume),
        statut=CreneauDepot.Statut.RESERVE,
    )


def test_capacite_insuffisante_et_entrepot_inactif_exclus(pme):
    expedition = _expedition(pme, volume="5")
    _entrepot(nom="Relais Plein", ville="Tunis", capacite_max_m3=Decimal("4"), latitude=36.81, longitude=10.19)
    _occuper(_entrepot(nom="Relais Saturé", ville="Tunis", capacite_max_m3=Decimal("10")), pme, "8")
    _entrepot(nom="Relais Libre", ville="Sfax", capacite_max_m3=Decimal("20"), latitude=34.74, longitude=10.76)
    _entrepot(nom="Relais Fermé", ville="Sfax", capacite_max_m3=Decimal("30"), actif=False)
    resultat = service.recommander(pme, expedition.pk)
    noms = [ligne.entrepot.nom for ligne in resultat["recommandations"]]
    assert "Relais Libre" in noms
    assert "Relais Saturé" not in noms
    assert "Relais Fermé" not in noms
    assert "Relais Plein" not in noms
    assert resultat["modele"] == "repli"


def test_reservation_echue_ne_bloque_plus_le_volume(pme):
    expedition = _expedition(pme, volume="5")
    entrepot = _entrepot(nom="Relais Libéré", capacite_max_m3=Decimal("10"), latitude=36.81, longitude=10.19)
    autre = _expedition(pme, volume="9", ville_depart="Bizerte")
    debut = timezone.now() - timedelta(days=3)
    CreneauDepot.objects.create(
        entrepot=entrepot,
        expedition=autre,
        debut=debut,
        fin=debut + timedelta(hours=2),
        fin_stockage_prevue=timezone.now() - timedelta(hours=1),
        volume_reserve=Decimal("9"),
        statut=CreneauDepot.Statut.RESERVE,
    )
    resultat = service.recommander(pme, expedition.pk)
    assert [ligne.entrepot.nom for ligne in resultat["recommandations"]] == ["Relais Libéré"]


def test_horaire_invalide_exclu(pme):
    expedition = _expedition(pme, volume="1")
    _entrepot(
        nom="Relais Sans Plage",
        horaire_ouverture=time(18, 0),
        horaire_fermeture=time(8, 0),
        capacite_max_m3=Decimal("10"),
    )
    ouvert = _entrepot(
        nom="Relais Ouvert",
        horaire_ouverture=time(8, 0),
        horaire_fermeture=time(18, 0),
        capacite_max_m3=Decimal("10"),
        latitude=36.9,
        longitude=10.2,
    )
    resultat = service.recommander(pme, expedition.pk)
    noms = [ligne.entrepot.nom for ligne in resultat["recommandations"]]
    assert noms == ["Relais Ouvert"]
    assert ouvert.nom == noms[0]
    assert "08:00" in resultat["recommandations"][0].explication
    assert resultat["recommandations"][0].distance is not None


def test_trois_meilleurs_seulement(pme):
    expedition = _expedition(pme, volume="1")
    for indice in range(4):
        _entrepot(nom=f"Relais {indice}", ville="Tunis", capacite_max_m3=Decimal("10"), latitude=36.8, longitude=10.2)
    resultat = service.recommander(pme, expedition.pk)
    assert len(resultat["recommandations"]) == 3
    assert all(ligne.score >= 0 for ligne in resultat["recommandations"])


def test_sans_poids_locaux_le_classement_lexical_repond(pme, monkeypatch):
    expedition = _expedition(pme, volume="1")
    _entrepot(nom="Relais Proche", ville="Tunis", capacite_max_m3=Decimal("10"), latitude=36.8, longitude=10.2)
    monkeypatch.setattr(service, "_modele_en_cache", lambda: False)

    with override_settings(SENTENCE_TRANSFORMERS_ACTIF=True):
        resultat = service.recommander(pme, expedition.pk)

    assert resultat["modele"] == "repli"
    assert resultat["recommandations"]


def test_modele_sentence_transformers_classe_la_fiche_proche(pme, monkeypatch):
    expedition = _expedition(pme, volume="1")
    _entrepot(nom="Entrepôt Nord", ville="Tunis", capacite_max_m3=Decimal("10"))
    _entrepot(nom="Entrepôt Sud", ville="Sfax", capacite_max_m3=Decimal("10"))
    monkeypatch.setattr(service, "_charger_modele", lambda: _Modele())
    with override_settings(SENTENCE_TRANSFORMERS_ACTIF=True):
        resultat = service.recommander(pme, expedition.pk)
    assert resultat["modele"] == "sentence-transformers"
    assert resultat["recommandations"][0].entrepot.nom == "Entrepôt Nord"


def test_expedition_dune_autre_pme_est_refusee(pme):
    autre = Utilisateur.objects.create_user("reco-autre@test.tn", "motdepasse123", role=Role.PME)
    expedition = _expedition(autre)
    _entrepot(nom="Relais Public", capacite_max_m3=Decimal("10"))
    resultat = service.recommander(pme, expedition.pk)
    assert resultat["erreur"] == "Expédition inconnue."
    assert resultat["recommandations"] == []


def test_page_et_permissions(client, pme, transporteur):
    expedition = _expedition(pme, volume="1")
    entrepot = _entrepot(
        nom="Relais Proposé",
        ville="Tunis",
        capacite_max_m3=Decimal("12"),
        latitude=36.82,
        longitude=10.2,
    )
    client.force_login(pme)
    page = client.get(reverse("warehouses:liste"))
    assert page.status_code == 200
    html = page.content.decode()
    assert "Décrivez votre besoin" not in html
    assert "Rechercher avec IA" in html
    assert "data-ia=" in html
    reponse = client.post(reverse("warehouses:recommander"), {"expedition": expedition.pk})
    corps = reponse.content.decode()
    assert reponse.status_code == 200
    assert "Relais Proposé" in corps
    assert f"{reverse('warehouses:reserver', args=[entrepot.pk])}?expedition={expedition.pk}" in corps
    assert "Réserver" in corps
    assert "recommandations-entrepots" in corps
    client.force_login(transporteur)
    refuse = client.post(reverse("warehouses:recommander"), {"expedition": expedition.pk})
    assert refuse.status_code == 403
    client.logout()
    anonyme = client.post(reverse("warehouses:recommander"), {"expedition": expedition.pk})
    assert anonyme.status_code == 302


def test_gabes_vers_zaghouan_prefere_le_sud(pme):
    expedition = _expedition(pme, volume="1", ville_depart="Gabès", latitude=None, longitude=None)
    expedition.adresse_arrivee.ville = "Zaghouan"
    expedition.adresse_arrivee.save(update_fields=["ville"])
    _entrepot(nom="Dépôt Gabès", ville="Gabès", capacite_max_m3=Decimal("20"), latitude=33.88, longitude=10.12)
    _entrepot(nom="Dépôt Médenine", ville="Médenine", capacite_max_m3=Decimal("20"), latitude=33.35, longitude=10.49)
    _entrepot(nom="Dépôt Sfax", ville="Sfax", capacite_max_m3=Decimal("20"), latitude=34.74, longitude=10.76)
    _entrepot(nom="Dépôt Raoued", ville="Raoued", capacite_max_m3=Decimal("20"), latitude=36.95, longitude=10.19)
    _entrepot(nom="Dépôt Lac", ville="Tunis", capacite_max_m3=Decimal("20"), latitude=36.83, longitude=10.23)
    resultat = service.recommander(pme, expedition.pk)
    noms = [ligne.entrepot.nom for ligne in resultat["recommandations"]]
    assert noms[0] == "Dépôt Gabès"
    assert "Dépôt Raoued" not in noms
    assert "Dépôt Lac" not in noms
    assert resultat["recommandations"][0].distance is not None
    assert resultat["recommandations"][0].distance < 5
    assert "centre de Gabès" in resultat["recommandations"][0].explication


def test_date_passee_refusee(pme):
    expedition = _expedition(pme)
    resultat = service.recommander(pme, expedition.pk, jour=timezone.localdate() - timedelta(days=1))
    assert "passé" in resultat["erreur"]


def test_la_recherche_quitte_la_requete_quand_celery_travaille(client, pme, settings, monkeypatch):
    settings.CELERY_TASK_ALWAYS_EAGER = False
    settings.SENTENCE_TRANSFORMERS_ACTIF = True
    monkeypatch.setattr("apps.warehouses.views.classement_immediat", lambda: False)
    expedition = _expedition(pme, volume="1")
    client.force_login(pme)

    class Calcul:
        def ready(self):
            return False

    monkeypatch.setattr(
        "apps.warehouses.views.calculer_recommandation_entrepots.delay",
        lambda *args, **kwargs: Calcul(),
    )
    reponse = client.post(reverse("warehouses:recommander"), {"expedition": expedition.pk})
    corps = reponse.content.decode()
    assert reponse.status_code == 200
    assert "Recherche des entrepôts en cours" in corps
    assert "recommandation-attente" in corps
