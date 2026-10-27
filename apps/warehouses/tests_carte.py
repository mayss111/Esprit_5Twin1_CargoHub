"""Carte et recherche des points relais, sans appel à OpenStreetMap."""

import json
import re
from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Utilisateur
from apps.core.roles import Role
from apps.shipments.models import Adresse, Expedition
from apps.warehouses.services.distance import distance_km
from apps.warehouses.tests import _entrepot

pytestmark = pytest.mark.django_db


def _expedition(pme, statut=Expedition.Statut.PUBLIEE, latitude=36.8, longitude=10.18):
    return Expedition.objects.create(
        pme=pme,
        adresse_depart=Adresse.objects.create(
            ligne="Rue de départ", ville="Tunis", latitude=latitude, longitude=longitude
        ),
        adresse_arrivee=Adresse.objects.create(ligne="Rue d'arrivée", ville="Sfax"),
        date_souhaitee=timezone.localdate() + timedelta(days=2),
        date_arrivee=timezone.localdate() + timedelta(days=3),
        statut=statut,
    )


def _marqueurs(html):
    trouve = re.search(r'id="marqueurs-entrepots"[^>]*>(.*?)</script>', html, re.DOTALL)
    return json.loads(trouve.group(1))


def test_distance_a_vol_doiseau():
    assert distance_km(36.8, 10.2, 36.8, 10.2) == 0
    assert 110 < distance_km(36.0, 10.0, 37.0, 10.0) < 112


def test_pme_voit_les_actifs_et_pas_les_inactifs(client, pme):
    _entrepot(nom="Relais Ouvert", ville="Tunis", latitude=36.8, longitude=10.18)
    ferme = _entrepot(nom="Relais Fermé", ville="Sfax", actif=False)
    client.force_login(pme)
    page = client.get(reverse("warehouses:liste"))
    assert page.status_code == 200
    html = page.content.decode()
    assert "Relais Ouvert" in html
    assert "Relais Fermé" not in html
    assert "OpenStreetMap" in html
    assert client.get(reverse("warehouses:detail", args=[ferme.pk])).status_code == 404


def test_recherche_nom_ville_et_gouvernorat(client, pme):
    _entrepot(nom="Hub Ariana", ville="Ariana", gouvernorat="Ariana", latitude=36.86, longitude=10.19)
    _entrepot(nom="Hub Sousse", ville="Sousse", gouvernorat="Sousse", latitude=35.82, longitude=10.64)
    client.force_login(pme)
    par_nom = client.get(reverse("warehouses:liste"), {"q": "Ariana"}).content.decode()
    assert "Hub Ariana" in par_nom
    assert "Hub Sousse" not in par_nom
    par_ville = client.get(reverse("warehouses:liste"), {"ville": "Sousse"}).content.decode()
    assert "Hub Sousse" in par_ville
    assert "Hub Ariana" not in par_ville
    par_gouvernorat = client.get(reverse("warehouses:liste"), {"gouvernorat": "Ariana"}).content.decode()
    assert "Hub Ariana" in par_gouvernorat
    assert "Hub Sousse" not in par_gouvernorat
    assert _marqueurs(par_gouvernorat)[0]["nom"] == "Hub Ariana"
    assert "data-filtre-auto" in par_gouvernorat
    par_adresse = client.get(reverse("warehouses:liste"), {"q": "Avenue Habib"}).content.decode()
    assert "Hub Ariana" in par_adresse
    assert "Hub Sousse" in par_adresse
    inconnu = client.get(reverse("warehouses:liste"), {"gouvernorat": "Paris"}).content.decode()
    assert "ne correspond" in inconnu
    assert "Hub Ariana" not in inconnu


def test_coordonnees_manquantes_sans_marqueur(client, pme):
    _entrepot(nom="Sans GPS", ville="Nabeul", gouvernorat="Nabeul")
    _entrepot(nom="Avec GPS", ville="Tunis", gouvernorat="Tunis", latitude=36.8, longitude=10.18)
    client.force_login(pme)
    html = client.get(reverse("warehouses:liste")).content.decode()
    noms = [point["nom"] for point in _marqueurs(html)]
    assert "Sans GPS" in html
    assert "Avec GPS" in noms
    assert "Sans GPS" not in noms


def test_expedition_ne_filtre_pas_les_entrepots(client, pme):
    expedition = _expedition(pme, latitude=None, longitude=None)
    _entrepot(nom="Tout près", ville="Tunis", latitude=36.81, longitude=10.19)
    _entrepot(nom="Très loin", ville="Tataouine", gouvernorat="Tataouine", latitude=32.93, longitude=10.45)
    client.force_login(pme)
    sans = client.get(reverse("warehouses:liste")).content.decode()
    html = client.get(reverse("warehouses:liste"), {"expedition": expedition.pk}).content.decode()
    assert "filtre-expedition" not in html
    assert "n'a pas de coordonnées" not in html
    assert "Tout près" in html and "Très loin" in html
    assert "Tout près" in sans and "Très loin" in sans
    assert f"expedition={expedition.pk}" in html
    detail = client.get(reverse("shipments:detail", args=[expedition.pk])).content.decode()
    assert "Trouver un point relais" in detail


def test_expedition_dune_autre_pme_est_refusee(client, pme):
    autre = Utilisateur.objects.create_user("autre-relais@test.tn", "motdepasse123", role=Role.PME)
    expedition = _expedition(autre)
    _entrepot(nom="Relais Public", ville="Sfax")
    client.force_login(pme)
    html = client.get(reverse("warehouses:liste"), {"expedition": expedition.pk}).content.decode()
    assert "Expédition inconnue" not in html
    assert f"expedition={expedition.pk}" not in html
    assert expedition.reference not in html
    assert "Rue de départ" not in html


def test_expedition_refusee_ne_donne_pas_de_distance(client, pme):
    expedition = _expedition(pme, statut=Expedition.Statut.REFUSEE)
    client.force_login(pme)
    html = client.get(reverse("warehouses:liste"), {"expedition": expedition.pk}).content.decode()
    assert "ne peut pas servir" not in html
    assert f"expedition={expedition.pk}" not in html
    assert "km à vol d'oiseau" not in html
    detail = client.get(reverse("shipments:detail", args=[expedition.pk])).content.decode()
    assert "Trouver un point relais" not in detail


def test_visiteur_est_renvoye_vers_la_connexion(client):
    entrepot = _entrepot()
    assert client.get(reverse("warehouses:liste")).status_code == 302
    assert client.get(reverse("warehouses:detail", args=[entrepot.pk])).status_code == 302


def test_detail_actif_sans_lien_de_reservation(client, pme):
    entrepot = _entrepot(nom="Relais Détail", latitude=36.8, longitude=10.18)
    client.force_login(pme)
    html = client.get(reverse("warehouses:detail", args=[entrepot.pk])).content.decode()
    assert "Relais Détail" in html
    assert "Réserver un créneau" in html
    assert "prochaine étape" not in html
    assert "OpenStreetMap" in html
    assert reverse("bo_warehouses:modifier", args=[entrepot.pk]) not in html
