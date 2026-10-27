import pytest
from django.test import RequestFactory
from django.urls import reverse

from apps.accounts.models import Utilisateur
from apps.core.roles import Role
from apps.shipments.models import Expedition
from apps.shipments.services.bon_pdf import generer_pdf, jeton_bon, lire_jeton, png_qr, textes_bon, url_verification


@pytest.fixture
def url_bon(expedition):
    request = RequestFactory().get("/")
    return url_verification(request, expedition)


def test_pdf_contient_la_reference_et_les_articles(expedition, url_bon):
    avant = Expedition.objects.count()
    modifie = expedition.updated_at
    pdf = generer_pdf(expedition, url_bon)
    expedition.refresh_from_db()

    assert pdf.startswith(b"%PDF")
    assert expedition.reference.encode() in pdf
    assert expedition.updated_at == modifie
    assert Expedition.objects.count() == avant
    textes = "\n".join(textes_bon(expedition, url_bon))
    assert "BON D'EXPÉDITION" in textes
    assert expedition.reference in textes
    assert "Cartons de vêtements" in textes
    assert "Zone industrielle" in textes
    assert "Atelier Sami" in textes
    assert "300" in textes
    assert "1.8" in textes
    assert "Textile" in textes


def test_qr_code_stable_et_sans_donnees_personnelles(expedition, url_bon):
    assert jeton_bon(expedition) == jeton_bon(expedition)
    assert lire_jeton(jeton_bon(expedition)) == expedition.pk
    assert png_qr(url_bon) == png_qr(url_bon)
    assert png_qr(url_bon).startswith(b"\x89PNG")
    assert "Zone industrielle" not in url_bon
    assert "pme@test.tn" not in url_bon
    assert "Cartons" not in url_bon
    assert generer_pdf(expedition, url_bon) == generer_pdf(expedition, url_bon)


def test_pme_telecharge_son_bon(client, pme, expedition):
    client.force_login(pme)
    reponse = client.get(reverse("shipments:bon", args=[expedition.pk]))
    assert reponse.status_code == 200
    assert reponse["Content-Type"] == "application/pdf"
    assert expedition.reference in reponse["Content-Disposition"]
    assert reponse.content.startswith(b"%PDF")
    assert expedition.reference.encode() in reponse.content


def test_admin_telecharge_le_bon(client, admin_user, expedition):
    client.force_login(admin_user)
    reponse = client.get(reverse("shipments:bon", args=[expedition.pk]))
    assert reponse.status_code == 200
    assert reponse.content.startswith(b"%PDF")


def test_autre_pme_ne_telecharge_pas(client, expedition, db):
    autre = Utilisateur.objects.create_user("autre-pme@test.tn", "motdepasse123", role=Role.PME)
    client.force_login(autre)
    reponse = client.get(reverse("shipments:bon", args=[expedition.pk]))
    assert reponse.status_code == 403
    assert b"%PDF" not in reponse.content


def test_visiteur_est_renvoye_vers_la_connexion(client, expedition):
    reponse = client.get(reverse("shipments:bon", args=[expedition.pk]))
    assert reponse.status_code == 302


@pytest.mark.parametrize("statut", ["REFUSEE", "A_VERIFIER", "BROUILLON", "ANNULEE"])
def test_bon_bloque_si_expedition_non_autorisee(client, pme, expedition, statut):
    expedition.statut = statut
    expedition.save(update_fields=["statut"])
    client.force_login(pme)
    reponse = client.get(reverse("shipments:bon", args=[expedition.pk]))
    assert reponse.status_code == 403
    assert "publiée et autorisée" in reponse.content.decode()


def test_liste_et_detail_affichent_le_bouton(client, pme, expedition):
    client.force_login(pme)
    liste = client.get(reverse("shipments:liste")).content.decode()
    detail = client.get(reverse("shipments:detail", args=[expedition.pk])).content.decode()
    assert "Télécharger le bon d'expédition PDF" in liste
    assert "Télécharger le bon d'expédition PDF" in detail


@pytest.mark.django_db
def test_verification_invalide(client):
    page = client.get(reverse("shipments:verifier", kwargs={"jeton": "jeton-inconnu"})).content.decode()
    assert "Référence invalide" in page


def test_verification_limitee_pour_un_tiers(client, expedition, transporteur):
    client.force_login(transporteur)
    page = client.get(reverse("shipments:verifier", kwargs={"jeton": jeton_bon(expedition)})).content.decode()
    assert "Référence valide" in page
    assert expedition.reference in page
    assert "Publiée" in page
    assert "Zone industrielle" not in page
    assert "Atelier Sami" not in page
    assert "pme@test.tn" not in page
    assert "Cartons de vêtements" not in page


def test_verification_complete_pour_la_pme_et_ladmin(client, pme, admin_user, expedition):
    jeton = jeton_bon(expedition)
    client.force_login(pme)
    page = client.get(reverse("shipments:verifier", kwargs={"jeton": jeton})).content.decode()
    assert "Zone industrielle" in page
    assert "Atelier Sami" in page
    assert "Cartons de vêtements" in page

    client.force_login(admin_user)
    page = client.get(reverse("shipments:verifier", kwargs={"jeton": jeton})).content.decode()
    assert "Zone industrielle" in page
    assert "Cartons de vêtements" in page


def test_visiteur_voit_la_validite_sans_adresse(client, expedition):
    page = client.get(reverse("shipments:verifier", kwargs={"jeton": jeton_bon(expedition)})).content.decode()
    assert "Référence valide" in page
    assert expedition.reference in page
    assert "Zone industrielle" not in page
    assert "pme@test.tn" not in page
