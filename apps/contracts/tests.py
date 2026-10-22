"""Tests du module Contrats & documents (M1) : génération, signature, PDF, documents, back-office."""

from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.accounts.models import Utilisateur
from apps.bookings.models import Reservation
from apps.contracts.models import Contrat, DocumentTransport
from apps.contracts.pdf import contrat_pdf
from apps.core.roles import Role

PDF = b"%PDF-1.4 test"


@pytest.fixture
def reservation(expedition, trajet):
    return Reservation.objects.create(
        expedition=expedition, trajet=trajet, statut=Reservation.Statut.ACCEPTEE, prix_convenu=Decimal("85")
    )


@pytest.fixture
def contrat(reservation):
    return Contrat.objects.create(reservation=reservation)


@pytest.fixture
def intrus(db):
    return Utilisateur.objects.create_user("intrus@test.tn", "motdepasse123", role=Role.TRANSPORTEUR)


def _document(nom="lettre.pdf", contenu=PDF):
    return SimpleUploadedFile(nom, contenu, content_type="application/pdf")


# ---------------------------------------------------------------- modèle et PDF (tests unitaires)


def test_parties_et_signature(contrat, pme, transporteur, intrus):
    assert contrat.partie(pme) == "PME" and contrat.partie(transporteur) == "TRANSPORTEUR"
    assert contrat.partie(intrus) is None and not contrat.peut_signer(intrus)
    assert contrat.sans_signature and not contrat.est_signe

    contrat.signer(pme)
    assert not contrat.peut_signer(pme) and contrat.peut_signer(transporteur)
    with pytest.raises(ValueError):
        contrat.signer(pme)
    contrat.signer(transporteur)
    assert contrat.est_signe and not contrat.sans_signature


def test_pdf_du_contrat(contrat):
    contenu = contrat_pdf(contrat)
    assert contenu.startswith(b"%PDF")
    assert len(contenu) > 1000


def test_str(contrat):
    assert str(contrat) == f"Contrat réservation #{contrat.reservation_id}"
    document = DocumentTransport.objects.create(
        reservation=contrat.reservation, type=DocumentTransport.Type.BON_LIVRAISON, fichier=_document()
    )
    assert str(document) == f"Bon de livraison #{document.pk}"


# ---------------------------------------------------------------- front-office (tests d'intégration)


def test_liste_propose_de_generer_le_contrat(client, reservation, pme):
    client.force_login(pme)
    reponse = client.get(reverse("contracts:liste"))
    assert list(reponse.context["reservations_sans_contrat"]) == [reservation]
    client.post(reverse("contracts:generer", args=[reservation.pk]))
    contrat = Contrat.objects.get(reservation=reservation)
    reponse = client.get(reverse("contracts:liste"))
    assert list(reponse.context["object_list"]) == [contrat]
    assert not reponse.context["reservations_sans_contrat"]


def test_generer_deux_fois_ne_cree_qu_un_contrat(client, reservation, transporteur):
    client.force_login(transporteur)
    client.post(reverse("contracts:generer", args=[reservation.pk]))
    reponse = client.post(reverse("contracts:generer", args=[reservation.pk]), follow=True)
    assert Contrat.objects.count() == 1
    assert "existe déjà" in reponse.content.decode()


def test_pas_de_contrat_avant_acceptation(client, reservation, pme):
    reservation.statut = Reservation.Statut.EN_ATTENTE
    reservation.save()
    client.force_login(pme)
    client.post(reverse("contracts:generer", args=[reservation.pk]))
    assert not Contrat.objects.exists()


def test_contrat_d_un_autre_introuvable(client, contrat, reservation, intrus):
    client.force_login(intrus)
    assert client.post(reverse("contracts:generer", args=[reservation.pk])).status_code == 404
    for nom in ["detail", "pdf", "supprimer"]:
        assert client.get(reverse(f"contracts:{nom}", args=[contrat.pk])).status_code == 404
    assert client.post(reverse("contracts:signer", args=[contrat.pk]), {"accepte": "oui"}).status_code == 404
    assert client.get(reverse("contracts:liste")).context["object_list"].count() == 0


def test_detail_du_contrat(client, contrat, pme):
    client.force_login(pme)
    reponse = client.get(reverse("contracts:detail", args=[contrat.pk]))
    assert reponse.status_code == 200
    assert reponse.context["partie"] == "PME" and reponse.context["peut_signer"]
    assert "Monastir" in reponse.content.decode()


def test_signer_sans_cocher_la_case(client, contrat, pme):
    client.force_login(pme)
    client.post(reverse("contracts:signer", args=[contrat.pk]))
    contrat.refresh_from_db()
    assert contrat.signe_par_pme_le is None


def test_signature_des_deux_parties_archive_le_pdf(client, contrat, pme, transporteur):
    client.force_login(pme)
    client.post(reverse("contracts:signer", args=[contrat.pk]), {"accepte": "oui"})
    reponse = client.post(reverse("contracts:signer", args=[contrat.pk]), {"accepte": "oui"}, follow=True)
    assert "déjà signé" in reponse.content.decode()
    contrat.refresh_from_db()
    assert contrat.signe_par_pme_le and not contrat.fichier

    client.force_login(transporteur)
    client.post(reverse("contracts:signer", args=[contrat.pk]), {"accepte": "oui"})
    contrat.refresh_from_db()
    assert contrat.est_signe and contrat.fichier.name.endswith(".pdf")

    reponse = client.get(reverse("contracts:pdf", args=[contrat.pk]))
    assert reponse["Content-Type"] == "application/pdf" and reponse.content.startswith(b"%PDF")


def test_telecharger_le_pdf(client, contrat, transporteur):
    client.force_login(transporteur)
    reponse = client.get(reverse("contracts:pdf", args=[contrat.pk]))
    assert reponse.status_code == 200 and reponse["Content-Type"] == "application/pdf"


def test_pdf_en_erreur(client, contrat, pme, monkeypatch):
    monkeypatch.setattr("apps.contracts.views.contrat_pdf", lambda c: 1 / 0)
    client.force_login(pme)
    reponse = client.get(reverse("contracts:pdf", args=[contrat.pk]), follow=True)
    assert "pas pu être généré" in reponse.content.decode()


def test_supprimer_un_contrat_non_signe(client, contrat, pme):
    client.force_login(pme)
    assert client.get(reverse("contracts:supprimer", args=[contrat.pk])).status_code == 200
    client.post(reverse("contracts:supprimer", args=[contrat.pk]))
    assert not Contrat.objects.exists()


def test_contrat_signe_non_supprimable(client, contrat, pme):
    contrat.signer(pme)
    client.force_login(pme)
    client.post(reverse("contracts:supprimer", args=[contrat.pk]))
    assert Contrat.objects.exists()


def test_ajouter_et_supprimer_un_document(client, contrat, transporteur):
    client.force_login(transporteur)
    url = reverse("contracts:detail", args=[contrat.pk])
    reponse = client.post(url, {"type": DocumentTransport.Type.LETTRE_VOITURE, "fichier": _document()})
    assert reponse.status_code == 302
    document = DocumentTransport.objects.get()
    assert document.reservation == contrat.reservation
    client.post(reverse("contracts:document_supprimer", args=[document.pk]))
    assert not DocumentTransport.objects.exists()


def test_document_invalide_refuse(client, contrat, pme):
    client.force_login(pme)
    reponse = client.post(
        reverse("contracts:detail", args=[contrat.pk]),
        {"type": DocumentTransport.Type.AUTRE, "fichier": _document("script.js", b"alert(1)")},
    )
    assert reponse.status_code == 200 and reponse.context["form_document"].errors
    assert not DocumentTransport.objects.exists()


def test_document_d_un_autre_non_supprimable(client, contrat, intrus):
    document = DocumentTransport.objects.create(
        reservation=contrat.reservation, type=DocumentTransport.Type.AUTRE, fichier=_document()
    )
    client.force_login(intrus)
    assert client.post(reverse("contracts:document_supprimer", args=[document.pk])).status_code == 404
    assert DocumentTransport.objects.exists()


# ---------------------------------------------------------------- back-office


def test_backoffice_contrats(client, admin_user, contrat, pme):
    client.force_login(admin_user)
    url = reverse("bo_contracts:liste")
    assert contrat in client.get(url, {"signature": "en_attente"}).context["object_list"]
    assert contrat not in client.get(url, {"signature": "signes"}).context["object_list"]
    assert client.get(reverse("bo_contracts:detail", args=[contrat.pk])).status_code == 200
    assert client.get(reverse("bo_contracts:pdf", args=[contrat.pk])).content.startswith(b"%PDF")
    assert client.get(reverse("bo_contracts:supprimer", args=[contrat.pk])).status_code == 200
    client.post(reverse("bo_contracts:supprimer", args=[contrat.pk]))
    assert not Contrat.objects.exists()


@pytest.mark.parametrize("nom", ["detail", "pdf", "supprimer"])
def test_backoffice_contrats_interdit_aux_utilisateurs(client, contrat, pme, nom):
    client.force_login(pme)
    assert client.get(reverse(f"bo_contracts:{nom}", args=[contrat.pk])).status_code == 403
