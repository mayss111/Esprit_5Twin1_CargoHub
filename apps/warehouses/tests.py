"""Tests du CRUD administrateur des entrepôts."""

from datetime import time
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone

from apps.warehouses.forms import EntrepotForm
from apps.warehouses.models import Entrepot

pytestmark = pytest.mark.django_db


def _donnees(**extra):
    donnees = {
        "nom": "Relais Lac",
        "description": "Point relais couvert",
        "adresse": "Rue du Lac",
        "ville": "Tunis",
        "gouvernorat": "Tunis",
        "code_postal": "1053",
        "latitude": "36.8",
        "longitude": "10.18",
        "capacite_max_m3": "25.000",
        "horaire_ouverture": "08:00",
        "horaire_fermeture": "18:00",
        "actif": "on",
    }
    donnees.update(extra)
    return donnees


def _entrepot(**extra):
    valeurs = {
        "nom": "Relais Test",
        "adresse": "Avenue Habib Bourguiba",
        "ville": "Monastir",
        "gouvernorat": "Monastir",
        "capacite_max_m3": Decimal("12.000"),
        "horaire_ouverture": time(8, 0),
        "horaire_fermeture": time(17, 0),
    }
    valeurs.update(extra)
    return Entrepot.objects.create(**valeurs)


def test_creation_valide(client, admin_user):
    client.force_login(admin_user)
    reponse = client.post(reverse("bo_warehouses:creer"), _donnees())
    entrepot = Entrepot.objects.get(nom="Relais Lac")
    assert reponse.status_code == 302
    assert reponse.url == reverse("bo_warehouses:detail", args=[entrepot.pk])
    assert entrepot.ville == "Tunis"
    assert entrepot.capacite_max_m3 == Decimal("25.000")
    assert entrepot.actif is True
    page = client.get(reponse.url)
    assert page.status_code == 200
    assert "Relais Lac" in page.content.decode()
    assert "est enregistré" in page.content.decode()


@pytest.mark.parametrize("capacite", ["0", "-1", "0.000"])
def test_capacite_nulle_ou_negative_refusee(capacite):
    formulaire = EntrepotForm(_donnees(capacite_max_m3=capacite))
    assert not formulaire.is_valid()
    assert "positive" in formulaire.errors["capacite_max_m3"][0]


def test_modele_refuse_une_capacite_nulle():
    entrepot = Entrepot(
        nom="Mauvais",
        adresse="Rue",
        ville="Sfax",
        capacite_max_m3=Decimal("0"),
        horaire_ouverture=time(8, 0),
        horaire_fermeture=time(18, 0),
    )
    with pytest.raises(ValidationError) as exc:
        entrepot.full_clean()
    assert "positive" in exc.value.message_dict["capacite_max_m3"][0]


def test_coordonnees_et_horaires_invalides():
    formulaire = EntrepotForm(
        _donnees(latitude="95", longitude="", horaire_ouverture="18:00", horaire_fermeture="08:00")
    )
    assert not formulaire.is_valid()
    assert "latitude" in formulaire.errors
    assert (
        "ouverture" in formulaire.errors["horaire_fermeture"][0].lower()
        or "après" in formulaire.errors["horaire_fermeture"][0]
    )


def test_doublon_nom_ville_refuse(admin_user):
    _entrepot(nom="Relais Lac", ville="Tunis")
    formulaire = EntrepotForm(_donnees())
    assert not formulaire.is_valid()
    assert "déjà ce nom" in formulaire.non_field_errors()[0]


def test_modification(client, admin_user):
    entrepot = _entrepot()
    client.force_login(admin_user)
    donnees = _donnees(nom="Relais Lac modifié", ville="Tunis", capacite_max_m3="30")
    reponse = client.post(reverse("bo_warehouses:modifier", args=[entrepot.pk]), donnees)
    entrepot.refresh_from_db()
    assert reponse.status_code == 302
    assert entrepot.nom == "Relais Lac modifié"
    assert entrepot.capacite_max_m3 == Decimal("30")
    assert Entrepot.objects.filter(pk=entrepot.pk).count() == 1


def test_desactivation_conserve_lhistorique(client, admin_user, pme):
    entrepot = _entrepot(nom="Relais Visible")
    client.force_login(admin_user)
    confirmation = client.get(reverse("bo_warehouses:desactiver", args=[entrepot.pk]))
    assert confirmation.status_code == 200
    assert "Désactiver" in confirmation.content.decode()
    reponse = client.post(reverse("bo_warehouses:desactiver", args=[entrepot.pk]))
    entrepot.refresh_from_db()
    assert reponse.status_code == 302
    assert entrepot.actif is False
    assert Entrepot.objects.filter(pk=entrepot.pk).exists()
    client.get(reponse.url)

    client.force_login(pme)
    page = client.get(reverse("warehouses:liste")).content.decode()
    assert "Relais Visible" not in page

    autre = _entrepot(nom="Relais Ouvert", ville="Sfax")
    page = client.get(reverse("warehouses:liste")).content.decode()
    assert "Relais Ouvert" in page
    assert autre.actif is True


def test_filtre_statut_et_nom(client, admin_user):
    _entrepot(nom="Port de Sfax", ville="Sfax", actif=True)
    _entrepot(nom="Ancien port", ville="Sfax", actif=False)
    client.force_login(admin_user)
    actifs = client.get(reverse("bo_warehouses:liste"), {"statut": "actif", "ville": "Sfax"}).content.decode()
    assert "Port de Sfax" in actifs
    assert "Ancien port" not in actifs
    recherche = client.get(reverse("bo_warehouses:liste"), {"q": "Ancien"}).content.decode()
    assert "Ancien port" in recherche
    assert "Port de Sfax" not in recherche
    assert "data-filtre-auto" in recherche
    assert ">Filtrer<" not in recherche
    par_adresse = client.get(reverse("bo_warehouses:liste"), {"adresse": "Habib Bourguiba"}).content.decode()
    assert "Port de Sfax" in par_adresse
    assert "Ancien port" in par_adresse
    lac = _entrepot(nom="Relais Lac", ville="Tunis", adresse="Rue du Lac", gouvernorat="Tunis")
    par_gouvernorat = client.get(reverse("bo_warehouses:liste"), {"gouvernorat": "Tunis"}).content.decode()
    assert lac.nom in par_gouvernorat
    assert "Port de Sfax" not in par_gouvernorat
    par_date = client.get(
        reverse("bo_warehouses:liste"),
        {"date": timezone.localdate().isoformat(), "q": "Lac"},
    ).content.decode()
    assert lac.nom in par_date
    assert "Port de Sfax" not in par_date
    inconnu = client.get(reverse("bo_warehouses:liste"), {"gouvernorat": "Paris"}).content.decode()
    assert "ne correspond" in inconnu


def test_pme_ne_cree_ni_ne_modifie(client, pme):
    entrepot = _entrepot()
    client.force_login(pme)
    assert client.get(reverse("bo_warehouses:liste")).status_code == 403
    assert client.get(reverse("bo_warehouses:creer")).status_code == 403
    assert client.post(reverse("bo_warehouses:creer"), _donnees()).status_code == 403
    assert client.post(reverse("bo_warehouses:modifier", args=[entrepot.pk]), _donnees()).status_code == 403
    assert client.post(reverse("bo_warehouses:desactiver", args=[entrepot.pk])).status_code == 403
    entrepot.refresh_from_db()
    assert entrepot.actif is True


def test_controle_de_saisie_hors_horaires_et_durees(client, admin_user):
    client.force_login(admin_user)
    page = client.get(reverse("bo_warehouses:creer")).content.decode()
    assert "novalidate" not in page
    assert 'minlength="3"' in page
    assert 'minlength="10"' in page
    assert 'inputmode="numeric"' in page
    incomplet = EntrepotForm(
        _donnees(
            nom="AB",
            description="court",
            adresse="Rue",
            ville="Tunis 1",
            code_postal="12",
            gouvernorat="",
            latitude="",
            longitude="",
        )
    )
    assert not incomplet.is_valid()
    assert "nom" in incomplet.errors
    assert "description" in incomplet.errors
    assert "adresse" in incomplet.errors
    assert "ville" in incomplet.errors
    assert "code_postal" in incomplet.errors
    assert "gouvernorat" in incomplet.errors
    assert "latitude" in incomplet.errors
    assert "longitude" in incomplet.errors
    sans_duree = EntrepotForm(_donnees(duree_stockage_max_heures="", delai_grace_minutes=""))
    assert sans_duree.is_valid()
    assert sans_duree.cleaned_data["duree_stockage_max_heures"] == 48
    assert sans_duree.cleaned_data["delai_grace_minutes"] == 30


def test_liste_admin_affiche_lentrepot(client, admin_user):
    entrepot = _entrepot(nom="Hub Radès", ville="Ben Arous")
    client.force_login(admin_user)
    page = client.get(reverse("bo_warehouses:liste")).content.decode()
    assert "Hub Radès" in page
    detail = client.get(reverse("bo_warehouses:detail", args=[entrepot.pk])).content.decode()
    assert "Taux d'occupation" in detail
    assert "Aucune réservation" in detail
    assert "Mouvements de colis" not in detail
