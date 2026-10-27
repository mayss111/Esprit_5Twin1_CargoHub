"""Clôture automatique et tableau d'occupation sans fenêtre de 48 heures."""

from datetime import datetime, time, timedelta
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.bookings.models import Notification
from apps.warehouses.models import CreneauDepot
from apps.warehouses.services.capacity import synthese_entrepot, volume_reserve
from apps.warehouses.services.reservation import reserver
from apps.warehouses.tasks import cloturer_reservations
from apps.warehouses.tests import _entrepot
from apps.warehouses.tests_reservation import _expedition_volume, _fin_texte

pytestmark = pytest.mark.django_db


def test_cinq_metres_cubes_taux_et_disponible(pme):
    entrepot = _entrepot(nom="Ariana Centre", ville="Ariana", capacite_max_m3=Decimal("100"))
    expedition = _expedition_volume(pme, "5", jours=4, rue="Rue de l'Ariana")
    creneau, erreur = reserver(
        pme, entrepot.pk, expedition.pk, expedition.date_souhaitee, "08:00", _fin_texte(expedition.date_souhaitee)
    )
    assert erreur == ""
    assert creneau.debut.date() > timezone.localdate() or creneau.debut > timezone.now()
    ligne = synthese_entrepot(entrepot)
    assert ligne["reserve"] == Decimal("5")
    assert ligne["disponible"] == Decimal("95")
    assert ligne["taux"] == Decimal("5.000")
    assert ligne["actives"] == 1


def test_cloture_passe_a_termine_et_libere_le_volume(pme):
    entrepot = _entrepot(nom="Depot cloture", ville="Sfax", capacite_max_m3=Decimal("100"))
    expedition = _expedition_volume(pme, "5", jours=4, rue="Rue cloture")
    creneau, erreur = reserver(
        pme, entrepot.pk, expedition.pk, expedition.date_souhaitee, "08:00", _fin_texte(expedition.date_souhaitee)
    )
    assert erreur == ""
    creneau.fin_stockage_prevue = timezone.now() - timedelta(minutes=5)
    creneau.save(update_fields=["fin_stockage_prevue"])
    assert volume_reserve(entrepot) == 0
    cloturer_reservations()
    creneau.refresh_from_db()
    assert creneau.statut == CreneauDepot.Statut.TERMINE
    assert volume_reserve(entrepot) == 0
    assert synthese_entrepot(entrepot)["disponible"] == Decimal("100")
    assert Notification.objects.filter(destinataire=pme, titre="Réservation terminée").exists()


def test_la_tache_ne_clot_pas_une_reservation_encore_valide(pme):
    entrepot = _entrepot(nom="Depot ouvert", ville="Nabeul", capacite_max_m3=Decimal("20"))
    expedition = _expedition_volume(pme, "2", jours=3, rue="Rue ouverte")
    creneau, erreur = reserver(
        pme, entrepot.pk, expedition.pk, expedition.date_souhaitee, "08:00", _fin_texte(expedition.date_souhaitee)
    )
    assert erreur == ""
    cloturer_reservations()
    creneau.refresh_from_db()
    assert creneau.statut == CreneauDepot.Statut.RESERVE
    assert volume_reserve(entrepot) == Decimal("2")


def test_dashboard_json_reprend_les_memes_chiffres(client, pme, admin_user):
    entrepot = _entrepot(nom="Ariana Centre", ville="Ariana", capacite_max_m3=Decimal("100"))
    expedition = _expedition_volume(pme, "5", jours=4, rue="Rue dashboard")
    confirme, erreur = reserver(
        pme,
        entrepot.pk,
        expedition.pk,
        expedition.date_souhaitee,
        "08:00",
        _fin_texte(expedition.date_souhaitee),
    )
    assert erreur == ""
    assert confirme is not None
    client.force_login(admin_user)
    page = client.get(reverse("bo_warehouses:occupation")).content.decode()
    assert "Taux d'occupation" in page
    assert "dès sa confirmation" in page
    assert 'type="date"' not in page
    assert 'data-col="reserve">5,000 m³' in page or 'data-col="reserve">5.000 m³' in page
    chiffres = client.get(reverse("bo_warehouses:occupation_chiffres")).json()
    assert chiffres["reserve"] == "5.000"
    assert chiffres["disponible"] == "95.000"
    assert chiffres["actives"] == 1
    assert chiffres["lignes"][0]["taux"] == "5.000"


def test_fin_egale_au_debut_du_creneau_est_refusee(pme):
    entrepot = _entrepot(capacite_max_m3=Decimal("10"))
    expedition = _expedition_volume(pme, "1", jours=2)
    fin = timezone.make_aware(datetime.combine(expedition.date_souhaitee, time(8, 0)))
    creneau, erreur = reserver(
        pme,
        entrepot.pk,
        expedition.pk,
        expedition.date_souhaitee,
        "08:00",
        fin,
    )
    assert creneau is None
    assert "postérieure au début" in erreur
