"""Capacité réservée dès la confirmation, jusqu'à la fin choisie."""

from datetime import datetime, time, timedelta
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.bookings.models import Notification
from apps.warehouses.models import CreneauDepot, MouvementColis
from apps.warehouses.services.capacity import disponible, synthese, synthese_entrepot, taux_occupation, volume_reserve
from apps.warehouses.services.reservation import reserver
from apps.warehouses.tests import _entrepot
from apps.warehouses.tests_reservation import _expedition_volume, _fin_texte, _preparer, _reserver

pytestmark = pytest.mark.django_db


def test_reservation_ajoute_le_volume_meme_si_le_depot_est_futur(client, pme, expedition, admin_user):
    _preparer(expedition, jours=6)
    entrepot = _entrepot(capacite_max_m3=Decimal("10"))
    client.force_login(pme)
    assert _reserver(client, entrepot, expedition).status_code == 302
    creneau = CreneauDepot.objects.get()
    assert creneau.volume_reserve == Decimal("1.800")
    assert creneau.fin_stockage_prevue > creneau.debut
    assert creneau.debut > timezone.now()
    assert volume_reserve(entrepot) == Decimal("1.800")
    assert disponible(entrepot) == Decimal("8.200")
    assert taux_occupation(entrepot) == Decimal("18.000")
    assert MouvementColis.objects.count() == 0
    assert Notification.objects.filter(destinataire=pme, titre="Réservation de dépôt confirmée").exists()
    client.force_login(admin_user)
    page = client.get(reverse("bo_warehouses:occupation")).content.decode()
    assert "1,800" in page or "1.800" in page
    assert "Taux d'occupation" in page
    assert 'name="date"' not in page
    assert "Confirmé" not in page
    assert "Déclaré" not in page


def test_annulation_libere_la_capacite(client, pme, expedition):
    _preparer(expedition)
    entrepot = _entrepot(capacite_max_m3=Decimal("10"))
    client.force_login(pme)
    _reserver(client, entrepot, expedition)
    creneau = CreneauDepot.objects.get()
    client.post(reverse("warehouses:depot_annuler", args=[creneau.pk]))
    creneau.refresh_from_db()
    assert creneau.statut == CreneauDepot.Statut.ANNULE
    assert volume_reserve(entrepot) == 0
    assert disponible(entrepot) == Decimal("10.000")


def test_deux_reservations_actives_s_additionnent_meme_a_des_jours_differents(pme):
    entrepot = _entrepot(nom="Depot cumul", ville="Tunis", capacite_max_m3=Decimal("100"))
    tot = _expedition_volume(pme, "5", jours=3, rue="Rue tot")
    tard = _expedition_volume(pme, "3", jours=10, rue="Rue tard")
    assert reserver(pme, entrepot.pk, tot.pk, tot.date_souhaitee, "08:00", _fin_texte(tot.date_souhaitee))[1] == ""
    assert reserver(pme, entrepot.pk, tard.pk, tard.date_souhaitee, "08:00", _fin_texte(tard.date_souhaitee))[1] == ""
    assert volume_reserve(entrepot) == Decimal("8")
    assert disponible(entrepot) == Decimal("92")
    assert synthese_entrepot(entrepot)["actives"] == 2


def test_un_entrepot_ne_change_pas_l_autre(pme):
    ariana = _entrepot(nom="Ariana Centre", ville="Ariana", capacite_max_m3=Decimal("100"))
    bizerte = _entrepot(nom="Bizerte Centre", ville="Bizerte", capacite_max_m3=Decimal("100"))
    expedition = _expedition_volume(pme, "5", jours=4, rue="Rue A")
    acceptee, erreur = reserver(
        pme,
        ariana.pk,
        expedition.pk,
        expedition.date_souhaitee,
        "08:00",
        _fin_texte(expedition.date_souhaitee),
    )
    assert erreur == ""
    assert acceptee is not None
    assert volume_reserve(bizerte) == 0
    assert synthese_entrepot(bizerte)["taux"] == Decimal("0.000")


def test_depassement_de_capacite_refuse(pme):
    entrepot = _entrepot(nom="Depot serre", ville="Kairouan", capacite_max_m3=Decimal("10"))
    premiere = _expedition_volume(pme, "6", jours=4, rue="Rue un")
    seconde = _expedition_volume(pme, "6", jours=4, rue="Rue deux")
    acceptee, erreur = reserver(
        pme,
        entrepot.pk,
        premiere.pk,
        premiere.date_souhaitee,
        "08:00",
        _fin_texte(premiere.date_souhaitee),
    )
    assert erreur == ""
    refuse, erreur = reserver(
        pme,
        entrepot.pk,
        seconde.pk,
        seconde.date_souhaitee,
        "10:00",
        _fin_texte(seconde.date_souhaitee),
    )
    assert refuse is None
    assert "insuffisante" in erreur
    assert volume_reserve(entrepot) == Decimal("6")
    assert disponible(entrepot) == Decimal("4")


def test_reservation_echue_ne_compte_plus_avant_la_tache(pme):
    entrepot = _entrepot(capacite_max_m3=Decimal("10"))
    expedition = _expedition_volume(pme, "4", jours=3)
    creneau, erreur = reserver(
        pme,
        entrepot.pk,
        expedition.pk,
        expedition.date_souhaitee,
        "08:00",
        _fin_texte(expedition.date_souhaitee),
    )
    assert erreur == ""
    creneau.fin_stockage_prevue = timezone.now() - timedelta(minutes=1)
    creneau.save(update_fields=["fin_stockage_prevue"])
    assert creneau.statut == CreneauDepot.Statut.RESERVE
    assert volume_reserve(entrepot) == 0
    assert disponible(entrepot) == Decimal("10.000")


def test_fin_anterieure_au_debut_est_refusee(pme):
    entrepot = _entrepot(capacite_max_m3=Decimal("10"))
    expedition = _expedition_volume(pme, "2", jours=3)
    fin = timezone.make_aware(datetime.combine(expedition.date_souhaitee, time(7, 0)))
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
    assert not CreneauDepot.objects.exists()


def test_resume_global_egal_a_la_somme_des_lignes(pme):
    ariana = _entrepot(nom="Ariana Centre", ville="Ariana", capacite_max_m3=Decimal("100"))
    bizerte = _entrepot(nom="Bizerte Centre", ville="Bizerte", capacite_max_m3=Decimal("40"))
    une = _expedition_volume(pme, "5", jours=4, rue="Rue Ariana")
    deux = _expedition_volume(pme, "2", jours=4, rue="Rue Bizerte")
    reserver(pme, ariana.pk, une.pk, une.date_souhaitee, "08:00", _fin_texte(une.date_souhaitee))
    reserver(pme, bizerte.pk, deux.pk, deux.date_souhaitee, "08:00", _fin_texte(deux.date_souhaitee))
    chiffres = synthese()
    assert chiffres["reserve"] == sum(ligne["reserve"] for ligne in chiffres["lignes"])
    assert chiffres["disponible"] == sum(ligne["disponible"] for ligne in chiffres["lignes"])
    assert chiffres["actives"] == sum(ligne["actives"] for ligne in chiffres["lignes"])
    assert chiffres["reserve"] == Decimal("7")
    assert chiffres["actives"] == 2


def test_occupation_filtre_par_nom(client, admin_user):
    _entrepot(nom="Relais Lac", ville="Tunis")
    _entrepot(nom="Relais Port", ville="Sfax")
    client.force_login(admin_user)
    page = client.get(reverse("bo_warehouses:occupation"), {"q": "Lac"}).content.decode()
    assert "data-filtre-auto" in page
    assert ">Filtrer<" not in page
    assert "Relais Lac" in page
    assert "Relais Port" not in page
    vide = client.get(reverse("bo_warehouses:occupation"), {"q": "introuvable"}).content.decode()
    assert "ne correspond" in vide


def test_pme_ne_voit_pas_le_dashboard(client, pme, admin_user, expedition):
    _preparer(expedition)
    entrepot = _entrepot()
    client.force_login(pme)
    assert client.get(reverse("bo_warehouses:occupation")).status_code == 403
    assert client.get(reverse("bo_warehouses:occupation_chiffres")).status_code == 403
    _reserver(client, entrepot, expedition)
    from apps.accounts.models import ProfilPME, Utilisateur
    from apps.core.roles import Role

    autre = Utilisateur.objects.create_user("loin@test.tn", "motdepasse123", role=Role.PME, first_name="Loin")
    ProfilPME.objects.create(utilisateur=autre, raison_sociale="Autre")
    client.force_login(autre)
    creneau = CreneauDepot.objects.get()
    assert client.post(reverse("warehouses:depot_annuler", args=[creneau.pk])).status_code == 404
    client.force_login(admin_user)
    assert client.get(reverse("bo_warehouses:occupation")).status_code == 200


def test_disponible_ne_devient_pas_negatif(pme):
    entrepot = _entrepot(capacite_max_m3=Decimal("5"))
    expedition = _expedition_volume(pme, "4", jours=3)
    reserver(
        pme,
        entrepot.pk,
        expedition.pk,
        expedition.date_souhaitee,
        "08:00",
        _fin_texte(expedition.date_souhaitee),
    )
    creneau = CreneauDepot.objects.get()
    assert disponible(entrepot) == Decimal("1.000")
    creneau.volume_reserve = Decimal("9")
    creneau.save(update_fields=["volume_reserve"])
    assert disponible(entrepot) == 0
