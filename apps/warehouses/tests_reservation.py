"""Réservation des créneaux de dépôt."""

from datetime import datetime, time, timedelta
from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Utilisateur
from apps.core.roles import Role
from apps.shipments.models import Adresse, ArticleExpedie, Expedition
from apps.warehouses.models import CreneauDepot, MouvementColis
from apps.warehouses.services.reservation import lister_creneaux, reserver
from apps.warehouses.tests import _entrepot

pytestmark = pytest.mark.django_db


def _preparer(expedition, jours=3, statut=Expedition.Statut.PUBLIEE):
    expedition.date_souhaitee = timezone.localdate() + timedelta(days=jours)
    expedition.date_arrivee = expedition.date_souhaitee + timedelta(days=1)
    expedition.statut = statut
    expedition.save(update_fields=["date_souhaitee", "date_arrivee", "statut"])
    return expedition


def _expedition_volume(pme, volume, jours=3, statut=Expedition.Statut.PUBLIEE, rue="Rue du test"):
    expedition = Expedition.objects.create(
        pme=pme,
        adresse_depart=Adresse.objects.create(ligne=rue, ville="Tunis"),
        adresse_arrivee=Adresse.objects.create(ligne="Rue d'arrivée", ville="Sfax"),
        date_souhaitee=timezone.localdate() + timedelta(days=jours),
        date_arrivee=timezone.localdate() + timedelta(days=jours + 1),
        statut=statut,
    )
    ArticleExpedie.objects.create(
        expedition=expedition,
        designation="Cartons",
        quantite=1,
        poids_kg=Decimal("10"),
        volume_m3=Decimal(volume),
    )
    return expedition


def _autre_pme():
    return Utilisateur.objects.create_user("autre-pme@test.tn", "motdepasse123", role=Role.PME, first_name="Nour")


def _fin_texte(jour):
    cible = max(jour + timedelta(days=1), timezone.localdate() + timedelta(days=2))
    return datetime.combine(cible, time(18, 0)).strftime("%Y-%m-%dT%H:%M")


def _reserver(client, entrepot, expedition, heure="08:00", jour=None):
    jour = jour or expedition.date_souhaitee
    return client.post(
        reverse("warehouses:reserver", args=[entrepot.pk]),
        {
            "expedition": expedition.pk,
            "date": jour.isoformat(),
            "creneau": heure,
            "fin_reservation": _fin_texte(jour),
        },
    )


def test_reservation_valide_dune_expedition_publiee(client, pme, expedition):
    _preparer(expedition)
    entrepot = _entrepot(nom="Relais Réservation")
    client.force_login(pme)
    reponse = _reserver(client, entrepot, expedition)
    assert reponse.status_code == 302
    creneau = CreneauDepot.objects.get()
    assert creneau.statut == CreneauDepot.Statut.RESERVE
    assert creneau.reference.startswith("DP-")
    assert creneau.expedition == expedition
    assert creneau.entrepot == entrepot
    assert creneau.heure_debut == time(8, 0)
    assert creneau.heure_fin == time(10, 0)
    assert creneau.volume_reserve == expedition.volume_total_m3
    assert MouvementColis.objects.count() == 0
    page = client.get(reponse.url)
    html = page.content.decode()
    assert "a été confirmée" in html
    assert creneau.reference in html
    assert "Relais Réservation" in html
    detail = client.get(reverse("shipments:detail", args=[expedition.pk])).content.decode()
    assert "Dépôt en point relais" in detail
    assert creneau.reference in detail


@pytest.mark.parametrize(
    "statut",
    [Expedition.Statut.ANNULEE, Expedition.Statut.REFUSEE, Expedition.Statut.A_VERIFIER, Expedition.Statut.BROUILLON],
)
def test_statuts_non_eligibles_refuses(client, pme, expedition, statut):
    _preparer(expedition, statut=statut)
    entrepot = _entrepot()
    client.force_login(pme)
    page = client.get(reverse("warehouses:reserver", args=[entrepot.pk]), {"expedition": expedition.pk})
    assert expedition.reference not in page.content.decode()
    reponse = _reserver(client, entrepot, expedition)
    assert reponse.status_code == 200
    assert "ne peut pas être déposée" in reponse.content.decode()
    assert not CreneauDepot.objects.exists()


def test_expedition_dune_autre_pme_reste_inconnue(client, pme, expedition):
    _preparer(expedition)
    autre = _autre_pme()
    etrangere = _expedition_volume(autre, "1", rue="Rue secrète de Nour")
    entrepot = _entrepot()
    client.force_login(pme)
    reponse = _reserver(client, entrepot, etrangere)
    html = reponse.content.decode()
    assert "Expédition inconnue" in html
    assert etrangere.reference not in html
    assert "Rue secrète" not in html
    assert not CreneauDepot.objects.exists()
    CreneauDepot.objects.create(
        entrepot=entrepot,
        expedition=etrangere,
        debut=timezone.now() + timedelta(days=2),
        fin=timezone.now() + timedelta(days=2, hours=1),
    )
    assert client.get(reverse("warehouses:depot", args=[CreneauDepot.objects.get().pk])).status_code == 404


def test_entrepot_inactif_introuvable(client, pme, expedition):
    _preparer(expedition)
    entrepot = _entrepot(actif=False)
    client.force_login(pme)
    assert client.get(reverse("warehouses:reserver", args=[entrepot.pk])).status_code == 404
    assert _reserver(client, entrepot, expedition).status_code == 404


def test_depart_passe_nest_pas_propose(client, pme, expedition):
    _preparer(expedition, jours=-1)
    entrepot = _entrepot(nom="Relais Départ Passé")
    client.force_login(pme)
    html = client.get(reverse("warehouses:reserver", args=[entrepot.pk])).content.decode()
    assert expedition.reference not in html
    assert "déjà passée" in _reserver(client, entrepot, expedition).content.decode()


def test_date_passee_refusee(client, pme, expedition):
    _preparer(expedition)
    entrepot = _entrepot()
    client.force_login(pme)
    reponse = _reserver(client, entrepot, expedition, jour=timezone.localdate() - timedelta(days=1))
    assert "passée" in reponse.content.decode()
    assert not CreneauDepot.objects.exists()


def test_creneau_hors_horaires(client, pme, expedition):
    _preparer(expedition)
    entrepot = _entrepot(horaire_ouverture=time(14, 0), horaire_fermeture=time(16, 0))
    client.force_login(pme)
    reponse = _reserver(client, entrepot, expedition, heure="09:00")
    assert "horaires" in reponse.content.decode()
    assert not CreneauDepot.objects.exists()


def test_creneau_passe_nest_pas_propose(expedition):
    _preparer(expedition, jours=0)
    entrepot = _entrepot()
    midi = timezone.make_aware(datetime.combine(timezone.localdate(), time(12, 0)))
    creneaux, erreur = lister_creneaux(entrepot, expedition, timezone.localdate(), maintenant=midi)
    assert erreur == ""
    valeurs = [creneau["valeur"] for creneau in creneaux]
    assert "08:00" not in valeurs
    assert "14:00" in valeurs


def test_volume_superieur_a_la_capacite(client, pme, expedition):
    _preparer(expedition)
    entrepot = _entrepot(capacite_max_m3=Decimal("1.000"))
    client.force_login(pme)
    reponse = client.get(
        reverse("warehouses:reserver", args=[entrepot.pk]),
        {"expedition": expedition.pk, "date": expedition.date_souhaitee.isoformat()},
    )
    assert "dépasse la capacité" in reponse.content.decode()
    assert not CreneauDepot.objects.exists()


def test_capacite_previsionnelle_sur_la_periode(client, pme):
    entrepot = _entrepot(capacite_max_m3=Decimal("10"))
    premiere = _expedition_volume(pme, "6", jours=4)
    seconde = _expedition_volume(pme, "6", jours=4)
    client.force_login(pme)
    assert _reserver(client, entrepot, premiere).status_code == 302
    refus = _reserver(client, entrepot, seconde, heure="10:00")
    assert "insuffisante" in refus.content.decode()
    suivante = _expedition_volume(pme, "8", jours=8)
    jour = timezone.localdate() + timedelta(days=7)
    encore = _reserver(client, entrepot, suivante, jour=jour)
    assert "insuffisante" in encore.content.decode()
    reservation = CreneauDepot.objects.get()
    assert client.post(reverse("warehouses:depot_annuler", args=[reservation.pk])).status_code == 302
    assert _reserver(client, entrepot, suivante, jour=jour).status_code == 302


def test_une_seule_reservation_active_puis_nouvelle_apres_annulation(client, pme, expedition):
    _preparer(expedition)
    entrepot = _entrepot()
    client.force_login(pme)
    assert _reserver(client, entrepot, expedition).status_code == 302
    doublon = _reserver(client, entrepot, expedition, heure="10:00")
    assert "déjà un dépôt réservé" in doublon.content.decode()
    assert CreneauDepot.objects.filter(statut=CreneauDepot.Statut.RESERVE).count() == 1
    reservation = CreneauDepot.objects.get()
    annulation = client.post(reverse("warehouses:depot_annuler", args=[reservation.pk]))
    assert annulation.status_code == 302
    reservation.refresh_from_db()
    assert reservation.statut == CreneauDepot.Statut.ANNULE
    assert CreneauDepot.objects.count() == 1
    assert _reserver(client, entrepot, expedition).status_code == 302
    assert CreneauDepot.objects.filter(statut=CreneauDepot.Statut.RESERVE).count() == 1


def test_contrainte_unique_en_cas_de_course(pme, expedition, monkeypatch):
    _preparer(expedition)
    entrepot = _entrepot()
    debut = timezone.make_aware(datetime.combine(expedition.date_souhaitee, time(9, 0)))
    CreneauDepot.objects.create(entrepot=entrepot, expedition=expedition, debut=debut, fin=debut + timedelta(hours=1))
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            CreneauDepot.objects.create(
                entrepot=entrepot,
                expedition=expedition,
                debut=debut + timedelta(hours=1),
                fin=debut + timedelta(hours=2),
            )
    monkeypatch.setattr("apps.warehouses.services.reservation.depot_bloquant", lambda *_args, **_kwargs: False)
    creneau, erreur = reserver(
        pme,
        entrepot.pk,
        expedition.pk,
        expedition.date_souhaitee,
        "10:00",
        _fin_texte(expedition.date_souhaitee),
    )
    assert creneau is None
    assert "déjà" in erreur
    assert CreneauDepot.objects.filter(statut=CreneauDepot.Statut.RESERVE).count() == 1


def test_acces_reserve_a_la_pme_et_liste_filtree(client, pme, expedition, admin_user, transporteur):
    _preparer(expedition)
    entrepot = _entrepot(nom="Relais Filtre")
    client.force_login(pme)
    reponse = _reserver(client, entrepot, expedition)
    client.get(reponse.url)
    reservation = CreneauDepot.objects.get()
    autre = _autre_pme()
    client.force_login(autre)
    assert client.get(reverse("warehouses:depot", args=[reservation.pk])).status_code == 404
    assert reservation.reference not in client.get(reverse("warehouses:mes_depots")).content.decode()
    client.force_login(transporteur)
    assert client.get(reverse("warehouses:mes_depots")).status_code == 403
    client.logout()
    assert client.get(reverse("warehouses:mes_depots")).status_code == 302
    client.force_login(pme)
    assert client.get(reverse("bo_warehouses:reservations")).status_code == 403
    html = client.get(reverse("warehouses:mes_depots"), {"q": reservation.reference}).content.decode()
    assert reservation.reference in html
    assert "Relais Filtre" in html
    vide = client.get(reverse("warehouses:mes_depots"), {"statut": "ANNULE"}).content.decode()
    assert "Aucune réservation" in vide
    client.force_login(admin_user)
    admin = client.get(reverse("bo_warehouses:reservations"), {"q": expedition.reference}).content.decode()
    assert reservation.reference in admin
    assert "Atelier Sami" in admin or pme.email in admin
    assert "data-filtre-auto" in admin
    assert ">Filtrer<" not in admin
    par_email = client.get(reverse("bo_warehouses:reservations"), {"email": pme.email}).content.decode()
    assert reservation.reference in par_email
    inconnu = client.get(reverse("bo_warehouses:reservations"), {"email": "absent@exemple.tn"}).content.decode()
    assert "ne correspond" in inconnu
    detail = client.get(reverse("bo_warehouses:reservation", args=[reservation.pk])).content.decode()
    assert "E-mail" in detail
    assert pme.email in detail
    assert "Aucun mouvement" not in detail


def test_annulation_admin_avec_motif_et_conservation(client, pme, expedition, admin_user):
    _preparer(expedition)
    entrepot = _entrepot()
    client.force_login(pme)
    _reserver(client, entrepot, expedition)
    reservation = CreneauDepot.objects.get()
    client.force_login(admin_user)
    url = reverse("bo_warehouses:reservation_annuler", args=[reservation.pk])
    assert client.get(url).status_code == 200
    reservation.refresh_from_db()
    assert reservation.statut == CreneauDepot.Statut.RESERVE
    court = client.post(url, {"motif": "court"})
    assert "10 caractères" in court.content.decode()
    reservation.refresh_from_db()
    assert reservation.statut == CreneauDepot.Statut.RESERVE
    confirme = client.post(url, {"motif": "Créneau devenu indisponible pour travaux."})
    assert confirme.status_code == 302
    reservation.refresh_from_db()
    assert reservation.statut == CreneauDepot.Statut.ANNULE
    assert "travaux" in reservation.motif_annulation
    assert CreneauDepot.objects.filter(pk=reservation.pk).exists()
