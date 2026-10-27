"""Tests M5 — suivi, preuve, incidents, avis et résumé IA."""

from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse

from apps.bookings.models import Reservation
from apps.core.evaluation import jeux
from apps.tracking.ai import analyser_sentiment
from apps.tracking.models import Avis, Incident, ResumeTransporteur, SuiviPosition
from apps.tracking.services import SuiviImpossible, ajouter_position, confirmer_livraison, deposer_preuve


def test_position_refuse_une_latitude_impossible(reservation):
    position = SuiviPosition(reservation=reservation, latitude=120, longitude=10)
    with pytest.raises(ValidationError):
        position.full_clean()


def test_incident_exige_une_description(reservation, pme):
    incident = Incident(reservation=reservation, declare_par=pme, type=Incident.Type.RETARD, description="court")
    with pytest.raises(ValidationError):
        incident.full_clean()


def test_transporteur_signale_une_position_et_passe_en_transit(reservation, transporteur):
    ajouter_position(reservation, transporteur, 35.82, 10.63)
    reservation.refresh_from_db()
    assert reservation.statut == Reservation.Statut.EN_TRANSIT
    assert reservation.positions.count() == 1


def test_pme_confirme_avec_le_bon_code(reservation, transporteur, pme):
    preuve = deposer_preuve(reservation, transporteur)
    confirmer_livraison(reservation, pme, preuve.code_otp)
    reservation.refresh_from_db()
    preuve.refresh_from_db()
    assert reservation.statut == Reservation.Statut.LIVREE
    assert preuve.confirmee_le is not None
    assert reservation.paiement.montant == Decimal("100.00")


def test_mauvais_code_ne_livre_pas(reservation, transporteur, pme):
    deposer_preuve(reservation, transporteur)
    with pytest.raises(SuiviImpossible):
        confirmer_livraison(reservation, pme, "000000")
    reservation.refresh_from_db()
    assert reservation.statut == Reservation.Statut.EN_TRANSIT


def test_une_autre_pme_ne_voit_pas_le_suivi(client, reservation, autre_pme):
    client.force_login(autre_pme)
    assert client.get(reverse("tracking:detail", args=[reservation.pk])).status_code == 404


def test_pme_ne_peut_pas_poster_une_position(client, reservation, pme):
    client.force_login(pme)
    reponse = client.post(
        reverse("tracking:detail", args=[reservation.pk]),
        {"action": "position", "latitude": 35, "longitude": 10},
    )
    assert reponse.status_code == 403


def test_page_suivi_et_declaration_incident(client, reservation, pme):
    client.force_login(pme)
    url = reverse("tracking:detail", args=[reservation.pk])
    assert client.get(url).status_code == 200
    reponse = client.post(url, {"action": "incident", "type": "RETARD", "description": "Deux heures de retard"})
    assert reponse.status_code == 302
    assert Incident.objects.filter(reservation=reservation, declare_par=pme).exists()


def test_incident_invalide_reste_sur_la_page(client, reservation, pme):
    client.force_login(pme)
    reponse = client.post(
        reverse("tracking:detail", args=[reservation.pk]),
        {"action": "incident", "type": "RETARD", "description": "court"},
    )
    assert reponse.status_code == 200
    assert "10 caractères" in reponse.content.decode()


def test_avis_apres_livraison_lance_le_resume(client, reservation, transporteur, pme):
    preuve = deposer_preuve(reservation, transporteur)
    confirmer_livraison(reservation, pme, preuve.code_otp)
    client.force_login(pme)
    reponse = client.post(
        reverse("tracking:detail", args=[reservation.pk]),
        {"action": "avis", "note": 5, "commentaire": "Livraison rapide, merci"},
    )
    assert reponse.status_code == 302
    avis = Avis.objects.get(reservation=reservation, auteur=pme)
    assert avis.sentiment == "POSITIF"
    assert ResumeTransporteur.objects.filter(transporteur=transporteur).exists()


def test_modification_et_suppression_incident(client, reservation, pme):
    incident = Incident.objects.create(
        reservation=reservation,
        declare_par=pme,
        type=Incident.Type.AUTRE,
        description="Colis ouvert à l'arrivée",
    )
    client.force_login(pme)
    modifier = reverse("tracking:incident_modifier", args=[incident.pk])
    assert client.post(modifier, {"type": "DOMMAGE", "description": "Carton abîmé sur un coin"}).status_code == 302
    incident.refresh_from_db()
    assert incident.type == Incident.Type.DOMMAGE
    assert client.post(reverse("tracking:incident_supprimer", args=[incident.pk])).status_code == 302
    assert not Incident.objects.filter(pk=incident.pk).exists()


def test_jeu_avis_aligne_sur_le_repli():
    assert len(jeux.AVIS) >= 30
    for texte, note, attendu in jeux.AVIS:
        assert analyser_sentiment(texte, note) == attendu


def test_backoffice_resout_un_incident(client, admin_user, reservation, pme):
    incident = Incident.objects.create(
        reservation=reservation, declare_par=pme, type=Incident.Type.RETARD, description="Retard de deux heures"
    )
    client.force_login(admin_user)
    url = reverse("bo_tracking:detail", args=[incident.pk])
    assert client.get(url).status_code == 200
    reponse = client.post(
        url, {"action": "enregistrer", "type": "RETARD", "description": incident.description, "statut": "RESOLU"}
    )
    assert reponse.status_code == 302
    incident.refresh_from_db()
    assert incident.statut == Incident.Statut.RESOLU
