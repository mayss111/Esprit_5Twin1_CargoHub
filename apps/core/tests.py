"""Tests transverses : toutes les pages répondent et les rôles sont respectés."""

import pytest
from django.urls import reverse

from config.urls import MODULES

PAGES_PME = [
    "shipments:liste",
    "warehouses:liste",
    "bookings:liste",
    "tenders:liste",
    "tracking:liste",
    "payments:liste",
    "insurance:liste",
    "messaging:liste",
    "loyalty:liste",
    "contracts:liste",
    "ecology:liste",
]
PAGES_TRANSPORTEUR = ["fleet:liste", "fleet:vehicules", "maintenance:liste", "bookings:liste", "tenders:liste"]


def test_accueil_public(client):
    assert client.get(reverse("core:accueil")).status_code == 200


@pytest.mark.parametrize("nom", PAGES_PME)
def test_pages_pme(client, pme, nom):
    client.force_login(pme)
    assert client.get(reverse(nom)).status_code == 200


@pytest.mark.parametrize("nom", PAGES_TRANSPORTEUR)
def test_pages_transporteur(client, transporteur, nom):
    client.force_login(transporteur)
    assert client.get(reverse(nom)).status_code == 200


def test_pme_ne_voit_pas_les_pages_transporteur(client, pme):
    client.force_login(pme)
    assert client.get(reverse("fleet:liste")).status_code == 403


@pytest.mark.parametrize("app", [m[2] for m in MODULES])
def test_backoffice_admin(client, admin_user, app):
    client.force_login(admin_user)
    assert client.get(reverse(f"bo_{app}:liste")).status_code == 200


def test_backoffice_interdit_aux_utilisateurs(client, pme):
    client.force_login(pme)
    assert client.get(reverse("dashboard:accueil")).status_code == 403
    assert client.get(reverse("bo_shipments:liste")).status_code == 403


def test_tableau_de_bord(client, admin_user, expedition):
    client.force_login(admin_user)
    reponse = client.get(reverse("dashboard:accueil"))
    assert reponse.status_code == 200
    assert "Expéditions" in reponse.content.decode()
