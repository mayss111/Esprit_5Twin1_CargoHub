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


# ---------- Besoins non fonctionnels (grille : sécurité, rôles, erreurs) ----------


@pytest.mark.parametrize("nom", ["bookings:liste", "dashboard:accueil", "accounts:profil"])
def test_anonyme_redirige_vers_connexion(client, nom):
    reponse = client.get(reverse(nom))
    assert reponse.status_code == 302
    assert reverse("accounts:connexion") in reponse.url


def test_page_404_personnalisee(client):
    reponse = client.get("/cette-page-n-existe-pas/")
    assert reponse.status_code == 404
    assert "Page introuvable" in reponse.content.decode()


def test_page_403_personnalisee(client, pme):
    client.force_login(pme)
    reponse = client.get(reverse("dashboard:accueil"))
    assert reponse.status_code == 403
    assert "Accès refusé" in reponse.content.decode()


def test_mots_de_passe_haches(pme):
    assert not pme.password.startswith("motdepasse")
    assert pme.check_password("motdepasse123")


def test_csrf_actif():
    from django.conf import settings

    assert "django.middleware.csrf.CsrfViewMiddleware" in settings.MIDDLEWARE


def test_accessibilite_page_accueil(client):
    html = client.get(reverse("core:accueil")).content.decode()
    for balise in [
        '<html lang="fr">',
        "<header>",
        '<main class="container py-4" id="contenu"',
        "<footer",
        'href="#contenu"',
    ]:
        assert balise in html


def test_commande_evaluer_ia(db):
    from io import StringIO

    from django.core.management import call_command

    sortie = StringIO()
    call_command("evaluer_ia", stdout=sortie)
    texte = sortie.getvalue()
    for membre in ["M1", "M2", "M3", "M4", "M5"]:
        assert membre in texte
    assert "F1" in texte and "MAE" in texte
