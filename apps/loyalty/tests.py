"""Tests M5 — points, parrainage et codes promo."""

from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse

from apps.loyalty.models import CodePromo
from apps.loyalty.services import CodeInvalide, ParrainageImpossible, calculer_reduction, parrainer

pytestmark = pytest.mark.django_db


def test_pourcentage_superieur_a_100_refuse():
    code = CodePromo(code="TROP", type=CodePromo.Type.POURCENTAGE, valeur=Decimal("150"))
    with pytest.raises(ValidationError):
        code.full_clean()


def test_reduction_montant_fixe():
    CodePromo.objects.create(code="MOINS20", type=CodePromo.Type.MONTANT, valeur=Decimal("20"))
    nouveau, promo = calculer_reduction(Decimal("100"), "moins20")
    assert nouveau == Decimal("80.00")
    assert promo.code == "MOINS20"


def test_code_inconnu():
    with pytest.raises(CodeInvalide):
        calculer_reduction(Decimal("50"), "INCONNU")


def test_on_ne_se_parraine_pas_soi_meme(pme):
    with pytest.raises(ParrainageImpossible):
        parrainer(pme, pme.email)


def test_parrainage_et_page(client, pme, transporteur):
    client.force_login(pme)
    assert client.get(reverse("loyalty:liste")).status_code == 200
    reponse = client.post(reverse("loyalty:liste"), {"email": transporteur.email})
    assert reponse.status_code == 302
    assert pme.parrainage.parrain == transporteur
    assert client.post(reverse("loyalty:liste"), {"email": transporteur.email}).status_code == 302


def test_admin_cree_modifie_et_supprime_un_code(client, admin_user):
    client.force_login(admin_user)
    assert client.get(reverse("bo_loyalty:liste")).status_code == 200
    creer = client.post(
        reverse("bo_loyalty:creer"),
        {
            "code": "rentree",
            "type": "POURCENTAGE",
            "valeur": "15",
            "montant_minimum": "0",
            "usage_unique": "",
            "actif": "on",
        },
    )
    assert creer.status_code == 302
    code = CodePromo.objects.get(code="RENTREE")
    assert (
        client.post(
            reverse("bo_loyalty:modifier", args=[code.pk]),
            {"code": "RENTREE", "type": "POURCENTAGE", "valeur": "20", "montant_minimum": "0", "actif": "on"},
        ).status_code
        == 302
    )
    code.refresh_from_db()
    assert code.valeur == Decimal("20")
    assert client.post(reverse("bo_loyalty:supprimer", args=[code.pk])).status_code == 302
    assert not CodePromo.objects.filter(pk=code.pk).exists()


def test_pme_ne_cree_pas_de_code(client, pme):
    client.force_login(pme)
    assert client.get(reverse("bo_loyalty:creer")).status_code == 403


@pytest.mark.django_db
def test_page_fidelite_affiche_les_points(client, pme):
    client.force_login(pme)
    assert "Vos points" in client.get(reverse("loyalty:liste")).content.decode()
