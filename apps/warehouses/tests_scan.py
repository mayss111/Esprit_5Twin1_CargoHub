"""Scan QR Code : entrée, sortie, durée de stockage. Aucun appel caméra."""

from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.shipments.models import Expedition
from apps.shipments.services.bon_pdf import jeton_bon
from apps.warehouses.models import CreneauDepot, MouvementColis
from apps.warehouses.services.scan import (
    analyser,
    confirmer_entree,
    confirmer_sortie,
    duree_stockage,
    etat_stockage,
    prolonger,
)
from apps.warehouses.tests import _entrepot
from apps.warehouses.tests_reservation import _preparer

pytestmark = pytest.mark.django_db


def _creneau(expedition, entrepot, debut):
    return CreneauDepot.objects.create(
        entrepot=entrepot,
        expedition=expedition,
        debut=debut,
        fin=debut + timedelta(hours=1),
        statut=CreneauDepot.Statut.RESERVE,
    )


def test_qr_invalide_et_lien_du_bon(expedition):
    assert analyser("pas-un-jeton")["erreur"] == "QR Code invalide."
    assert MouvementColis.objects.count() == 0
    lien = f"http://localhost/expeditions/verifier/{jeton_bon(expedition)}/"
    assert analyser(lien)["expedition"].pk == expedition.pk


@pytest.mark.parametrize("statut", [Expedition.Statut.ANNULEE, Expedition.Statut.REFUSEE])
def test_expedition_annulee_ou_refusee(expedition, statut):
    expedition.statut = statut
    expedition.save(update_fields=["statut"])
    assert "ne peut pas être déposée" in analyser(jeton_bon(expedition))["erreur"]


def test_entree_sans_reservation(expedition):
    assert analyser(jeton_bon(expedition))["erreur"] == "Aucune réservation de dépôt valide."


def test_entree_valide_puis_duree_et_sortie(admin_user, expedition):
    _preparer(expedition)
    maintenant = timezone.now()
    entrepot = _entrepot()
    _creneau(expedition, entrepot, maintenant - timedelta(minutes=20))
    mouvement, erreur = confirmer_entree(jeton_bon(expedition), admin_user, maintenant=maintenant)
    assert erreur == ""
    assert mouvement.type == MouvementColis.Type.ENTREE
    assert mouvement.ouvert is True
    expedition.refresh_from_db()
    assert expedition.statut == Expedition.Statut.PUBLIEE
    assert CreneauDepot.objects.get().statut == CreneauDepot.Statut.EFFECTUE
    assert entrepot.volume_present_m3() == expedition.volume_total_m3
    doublon, message = confirmer_entree(jeton_bon(expedition), admin_user, maintenant=maintenant)
    assert doublon is None
    assert message == "Une entrée est déjà enregistrée."
    mouvement.date = maintenant - timedelta(hours=5)
    mouvement.save(update_fields=["date"])
    sortie, erreur = confirmer_sortie(jeton_bon(expedition), admin_user, maintenant=maintenant)
    assert erreur == ""
    assert sortie.type == MouvementColis.Type.SORTIE
    assert duree_stockage(mouvement, sortie) == timedelta(hours=5)
    assert entrepot.volume_present_m3() == 0
    encore, message = confirmer_sortie(jeton_bon(expedition), admin_user, maintenant=maintenant)
    assert encore is None
    assert message == "Ce colis est déjà sorti."


def test_sortie_sans_entree(admin_user, expedition):
    _creneau(expedition, _entrepot(), timezone.now())
    mouvement, erreur = confirmer_sortie(jeton_bon(expedition), admin_user)
    assert mouvement is None
    assert erreur == "Aucune entrée n'est enregistrée."
    assert MouvementColis.objects.count() == 0


def test_arrivee_hors_creneau(admin_user, expedition):
    maintenant = timezone.now()
    _creneau(expedition, _entrepot(), maintenant - timedelta(hours=3))
    refuse, erreur = confirmer_entree(jeton_bon(expedition), admin_user, maintenant=maintenant)
    assert refuse is None
    assert "2 heures" in erreur
    assert MouvementColis.objects.count() == 0
    accepte, erreur = confirmer_entree(
        jeton_bon(expedition),
        admin_user,
        exceptionnel=True,
        motif="Quai occupé, arrivée acceptée par l'administrateur.",
        maintenant=maintenant,
    )
    assert erreur == ""
    assert accepte.exceptionnel is True


def test_depassement_48_heures_sans_sortie_automatique(admin_user, expedition):
    maintenant = timezone.now()
    moment_entree = maintenant - timedelta(hours=49)
    _creneau(expedition, _entrepot(duree_stockage_max_heures=48), moment_entree)
    entree, erreur = confirmer_entree(jeton_bon(expedition), admin_user, maintenant=moment_entree)
    assert erreur == ""
    assert etat_stockage(entree, maintenant)["depasse"] is True
    assert MouvementColis.objects.filter(type=MouvementColis.Type.SORTIE).count() == 0
    entree.date = maintenant - timedelta(hours=43)
    entree.save(update_fields=["date"])
    assert etat_stockage(entree, maintenant)["approche"] is True
    refuse, message = prolonger(entree.pk, 4, "court")
    assert refuse is None
    assert "10 caractères" in message
    prolonge, message = prolonger(entree.pk, 12, "Le transporteur récupère le colis demain matin.")
    assert message == ""
    assert prolonge.prolongation_heures == 12
    assert etat_stockage(prolonge, maintenant)["depasse"] is False


def test_scan_http_ne_confirme_pas_sans_bouton(client, admin_user, pme, expedition):
    from apps.accounts.models import ProfilPME, Utilisateur
    from apps.core.roles import Role

    _creneau(expedition, _entrepot(), timezone.now() - timedelta(minutes=15))
    jeton = jeton_bon(expedition)
    client.force_login(pme)
    assert client.get(reverse("bo_warehouses:scanner")).status_code == 403
    assert client.post(reverse("bo_warehouses:scanner"), {"jeton": jeton, "confirmer_entree": "1"}).status_code == 403
    assert MouvementColis.objects.count() == 0
    client.force_login(admin_user)
    lecture = client.post(reverse("bo_warehouses:scanner"), {"jeton": jeton, "identifier": "1"})
    assert lecture.status_code == 200
    assert "Confirmer l'entrée" in lecture.content.decode()
    assert MouvementColis.objects.count() == 0
    confirme = client.post(reverse("bo_warehouses:scanner"), {"jeton": jeton, "confirmer_entree": "1"})
    assert confirme.status_code == 302
    assert MouvementColis.objects.filter(type=MouvementColis.Type.ENTREE).count() == 1
    expedition.refresh_from_db()
    assert expedition.statut == Expedition.Statut.PUBLIEE
    client.force_login(pme)
    depot = CreneauDepot.objects.get()
    html = client.get(reverse("warehouses:depot", args=[depot.pk])).content.decode()
    assert "Entrée" in html
    assert expedition.reference in client.get(reverse("warehouses:mes_depots")).content.decode()
    autre = Utilisateur.objects.create_user("autre@test.tn", "motdepasse123", role=Role.PME, first_name="Autre")
    ProfilPME.objects.create(utilisateur=autre, raison_sociale="Autre atelier")
    client.force_login(autre)
    assert client.get(reverse("warehouses:depot", args=[depot.pk])).status_code == 404
