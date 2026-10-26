"""Tests M5 — paiement, facture, commission, code promo."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone

from apps.loyalty.models import CodePromo, Parrainage, PointsFidelite
from apps.payments.models import Commission, Paiement
from apps.payments.services import PaiementImpossible, appliquer_code, assurer_paiement, encaisser, rembourser
from apps.tracking.services import confirmer_livraison, deposer_preuve


def test_montant_negatif_refuse():
    paiement = Paiement(montant=Decimal("-1"))
    with pytest.raises(ValidationError):
        paiement.full_clean()


def test_encaissement_cree_facture_commission_et_points(reservation, pme):
    paiement = assurer_paiement(reservation)
    encaisser(paiement)
    paiement.refresh_from_db()
    assert paiement.statut == Paiement.Statut.PAYE
    assert paiement.facture.numero.startswith("CH-")
    assert paiement.facture.fichier
    assert paiement.commission.montant_commission == Decimal("8.00")
    assert paiement.commission.montant_transporteur == Decimal("92.00")
    assert PointsFidelite.objects.get(utilisateur=pme).solde == 100


def test_code_promo_reduit_le_montant(reservation):
    CodePromo.objects.create(code="BIENVENUE", type=CodePromo.Type.POURCENTAGE, valeur=Decimal("10"))
    paiement = assurer_paiement(reservation)
    appliquer_code(paiement, "bienvenue")
    paiement.refresh_from_db()
    assert paiement.montant == Decimal("90.00")
    assert paiement.code_promo == "BIENVENUE"


def test_code_expire_refuse(reservation):
    CodePromo.objects.create(
        code="PERIME",
        valeur=Decimal("5"),
        date_expiration=timezone.localdate() - timedelta(days=1),
    )
    paiement = assurer_paiement(reservation)
    with pytest.raises(PaiementImpossible):
        appliquer_code(paiement, "PERIME")


def test_parrain_recoit_50_points_au_premier_paiement(reservation, pme, transporteur):
    Parrainage.objects.create(parrain=transporteur, filleul=pme)
    encaisser(assurer_paiement(reservation))
    assert PointsFidelite.objects.get(utilisateur=transporteur).solde == 50
    assert Parrainage.objects.get(filleul=pme).recompense_versee


def test_remboursement_retire_les_points(reservation, pme):
    paiement = encaisser(assurer_paiement(reservation))
    rembourser(paiement)
    paiement.refresh_from_db()
    assert paiement.statut == Paiement.Statut.REMBOURSE
    assert PointsFidelite.objects.get(utilisateur=pme).solde == 0


def test_autre_pme_ne_voit_pas_le_paiement(client, reservation, autre_pme):
    paiement = assurer_paiement(reservation)
    client.force_login(autre_pme)
    assert client.get(reverse("payments:detail", args=[paiement.pk])).status_code == 404


def test_pme_paie_depuis_la_page(client, reservation, pme):
    preuve_reservee = assurer_paiement(reservation)
    client.force_login(pme)
    url = reverse("payments:detail", args=[preuve_reservee.pk])
    assert client.get(url).status_code == 200
    assert client.post(url, {"action": "payer"}).status_code == 302
    preuve_reservee.refresh_from_db()
    assert preuve_reservee.statut == Paiement.Statut.PAYE
    facture = client.get(reverse("payments:facture", args=[preuve_reservee.pk]))
    assert facture.status_code == 200
    assert facture["Content-Type"] == "application/pdf"
    assert b"".join(facture.streaming_content).startswith(b"%PDF")


def test_transporteur_ne_peut_pas_encaisser(client, reservation, transporteur):
    paiement = assurer_paiement(reservation)
    client.force_login(transporteur)
    assert client.post(reverse("payments:detail", args=[paiement.pk]), {"action": "payer"}).status_code == 403


def test_admin_verse_la_commission(client, admin_user, reservation):
    paiement = encaisser(assurer_paiement(reservation))
    client.force_login(admin_user)
    url = reverse("bo_payments:detail", args=[paiement.pk])
    assert client.get(url).status_code == 200
    assert client.post(url, {"action": "verser"}).status_code == 302
    assert Commission.objects.get(paiement=paiement).versee


def test_livraison_prepare_le_paiement(reservation, transporteur, pme):
    preuve = deposer_preuve(reservation, transporteur)
    confirmer_livraison(reservation, pme, preuve.code_otp)
    assert Paiement.objects.filter(reservation=reservation, statut=Paiement.Statut.EN_ATTENTE).exists()
