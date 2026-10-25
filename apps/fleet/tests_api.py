"""Tests de l'API REST du module Flotte — JWT, rôles, pagination, erreurs."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import Utilisateur
from apps.bookings import services as reservations
from apps.bookings.models import Reservation
from apps.core.roles import Role
from apps.fleet.models import FacteurEmission, Trajet, Vehicule

JETON_URL = "/api/token/"


def client_api(utilisateur=None):
    client = APIClient()
    if utilisateur:
        reponse = client.post(JETON_URL, {"email": utilisateur.email, "password": "motdepasse123"}, format="json")
        assert reponse.status_code == 200, reponse.content
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {reponse.data['access']}")
    return client


DONNEES_TRAJET = {
    "ville_depart": "Sousse",
    "ville_arrivee": "Tunis",
    "capacite_dispo_kg": "1500",
    "capacite_dispo_m3": "10",
    "prix_indicatif": "90",
}


def donnees_trajet(vehicule, **extras):
    base = {**DONNEES_TRAJET, "vehicule": vehicule.pk, "date_depart": (timezone.now() + timedelta(days=3)).isoformat()}
    base.update(extras)
    return base


@pytest.mark.django_db
class TestAuthJWT:
    def test_sans_jeton_401(self):
        reponse = client_api().get("/api/fleet/vehicules/")
        assert reponse.status_code == 401

    def test_mauvais_mot_de_passe_401(self, transporteur):
        client = APIClient()
        reponse = client.post(JETON_URL, {"email": transporteur.email, "password": "faux"}, format="json")
        assert reponse.status_code == 401


@pytest.mark.django_db
class TestVehiculesAPI:
    def test_transporteur_cree_vehicule(self, transporteur):
        reponse = client_api(transporteur).post(
            "/api/fleet/vehicules/",
            {"type": "CAMION", "immatriculation": "999 TU 1111", "capacite_kg": 2000, "capacite_m3": "12"},
            format="json",
        )
        assert reponse.status_code == 201
        assert Vehicule.objects.get(immatriculation="999 TU 1111").transporteur == transporteur

    def test_immatriculation_unique_422(self, transporteur, vehicule):
        client = client_api(transporteur)
        reponse = client.post(
            "/api/fleet/vehicules/",
            {"type": "CAMION", "immatriculation": vehicule.immatriculation, "capacite_kg": 2000, "capacite_m3": "12"},
            format="json",
        )
        assert reponse.status_code == 422

    def test_pme_n_peut_pas_creer(self, pme):
        reponse = client_api(pme).post(
            "/api/fleet/vehicules/",
            {"type": "CAMION", "immatriculation": "AAA", "capacite_kg": 1, "capacite_m3": "1"},
            format="json",
        )
        assert reponse.status_code == 403

    def test_transporteur_ne_voit_que_sa_flotte(self, transporteur, vehicule):
        autre = Utilisateur.objects.create_user("autre@test.tn", "motdepasse123", role=Role.TRANSPORTEUR)
        Vehicule.objects.create(
            transporteur=autre, type=Vehicule.Type.CAMION, immatriculation="ZZZ", capacite_kg=100, capacite_m3=1
        )
        reponse = client_api(transporteur).get("/api/fleet/vehicules/")
        immatriculations = [v["immatriculation"] for v in reponse.data["results"]]
        assert immatriculations == [vehicule.immatriculation]

    def test_admin_valide_vehicule(self, admin_user, vehicule):
        reponse = client_api(admin_user).patch(
            f"/api/fleet/vehicules/{vehicule.pk}/statut/", {"statut": "NON_CONFORME"}, format="json"
        )
        assert reponse.status_code == 200
        vehicule.refresh_from_db()
        assert vehicule.statut == Vehicule.Statut.NON_CONFORME and not vehicule.conforme

    def test_transporteur_ne_peut_pas_valider(self, transporteur, vehicule):
        reponse = client_api(transporteur).patch(
            f"/api/fleet/vehicules/{vehicule.pk}/statut/", {"statut": "ACTIF"}, format="json"
        )
        assert reponse.status_code == 403

    def test_statut_invalide_422(self, admin_user, vehicule):
        reponse = client_api(admin_user).patch(
            f"/api/fleet/vehicules/{vehicule.pk}/statut/", {"statut": "VOL"}, format="json"
        )
        assert reponse.status_code == 422

    def test_vehicule_inconnu_404(self, transporteur):
        reponse = client_api(transporteur).get("/api/fleet/vehicules/999999/")
        assert reponse.status_code == 404

    def test_vehicule_d_un_autre_404(self, transporteur):
        autre = Utilisateur.objects.create_user("x@test.tn", "motdepasse123", role=Role.TRANSPORTEUR)
        v = Vehicule.objects.create(
            transporteur=autre, type=Vehicule.Type.CAMION, immatriculation="YYY", capacite_kg=100, capacite_m3=1
        )
        assert client_api(transporteur).get(f"/api/fleet/vehicules/{v.pk}/").status_code == 404

    def test_vehicule_lie_a_un_trajet_ne_peut_pas_etre_supprime(self, transporteur, vehicule, trajet):
        reponse = client_api(transporteur).delete(f"/api/fleet/vehicules/{vehicule.pk}/")
        assert reponse.status_code == 409
        assert Vehicule.objects.filter(pk=vehicule.pk).exists()

    def test_liste_paginiee(self, transporteur, vehicule):
        reponse = client_api(transporteur).get("/api/fleet/vehicules/")
        assert {"count", "results"} <= set(reponse.data)

    def test_admin_liste_non_conformes(self, admin_user, vehicule):
        vehicule.statut = Vehicule.Statut.NON_CONFORME
        vehicule.save()
        reponse = client_api(admin_user).get("/api/fleet/vehicules/non_conformes/")
        assert reponse.status_code == 200
        assert reponse.data["results"][0]["statut"] == "NON_CONFORME"


@pytest.mark.django_db
class TestTrajetsAPI:
    def test_transporteur_publie_trajet(self, transporteur, vehicule):
        reponse = client_api(transporteur).post("/api/fleet/trajets/", donnees_trajet(vehicule), format="json")
        assert reponse.status_code == 201
        trajet = Trajet.objects.get(pk=reponse.data["id"])
        assert trajet.statut == Trajet.Statut.OUVERT
        assert Decimal(trajet.capacite_totale_kg) == Decimal("1500")

    def test_vehicule_non_conforme_refuse(self, transporteur, vehicule):
        vehicule.statut = Vehicule.Statut.NON_CONFORME
        vehicule.conforme = False
        vehicule.save()
        reponse = client_api(transporteur).post("/api/fleet/trajets/", donnees_trajet(vehicule), format="json")
        assert reponse.status_code == 422

    def test_vehicule_d_un_autre_refuse(self, transporteur, vehicule):
        autre = Utilisateur.objects.create_user("z@test.tn", "motdepasse123", role=Role.TRANSPORTEUR)
        vehicule.transporteur = autre
        vehicule.immatriculation = "WWW"
        vehicule.save()
        reponse = client_api(transporteur).post("/api/fleet/trajets/", donnees_trajet(vehicule), format="json")
        assert reponse.status_code == 403

    def test_capacite_sup_vehicule_422(self, transporteur, vehicule):
        donnees = donnees_trajet(vehicule, capacite_dispo_kg="9999999")
        reponse = client_api(transporteur).post("/api/fleet/trajets/", donnees, format="json")
        assert reponse.status_code == 422

    def test_date_passee_422(self, transporteur, vehicule):
        donnees = donnees_trajet(vehicule, date_depart=(timezone.now() - timedelta(days=1)).isoformat())
        reponse = client_api(transporteur).post("/api/fleet/trajets/", donnees, format="json")
        assert reponse.status_code == 422

    def test_capacite_tient_compte_de_la_place_reservee(self, transporteur, trajet, expedition):
        # Une réservation acceptée par le module M4 retire sa place du trajet.
        reservation = reservations.reserver(expedition, trajet)
        reservations.changer_statut(reservation, Reservation.Statut.ACCEPTEE, par=transporteur)
        trajet.refresh_from_db()
        reserve = expedition.poids_total_kg
        client = client_api(transporteur)
        url = f"/api/fleet/trajets/{trajet.pk}/"

        assert client.patch(url, {"capacite_totale_kg": str(reserve - 1)}, format="json").status_code == 422
        assert client.patch(url, {"capacite_dispo_kg": "2950"}, format="json").status_code == 422  # > 3000 kg

        reponse = client.patch(url, {"capacite_dispo_kg": "1500"}, format="json")
        assert reponse.status_code == 200
        trajet.refresh_from_db()
        assert trajet.capacite_dispo_kg == Decimal("1500")
        assert trajet.capacite_totale_kg == Decimal("1500") + reserve

    def test_trajet_avec_reservation_acceptee_non_annulable(self, transporteur, trajet, expedition):
        reservation = reservations.reserver(expedition, trajet)
        reservations.changer_statut(reservation, Reservation.Statut.ACCEPTEE, par=transporteur)
        assert client_api(transporteur).delete(f"/api/fleet/trajets/{trajet.pk}/").status_code == 422
        trajet.refresh_from_db()
        assert trajet.statut == Trajet.Statut.OUVERT

    def test_annulation_trajet(self, transporteur, trajet):
        reponse = client_api(transporteur).delete(f"/api/fleet/trajets/{trajet.pk}/")
        assert reponse.status_code == 204
        trajet.refresh_from_db()
        assert trajet.statut == Trajet.Statut.ANNULE

    def test_pme_recherche_compatibles(self, pme, trajet):
        reponse = client_api(pme).get(
            "/api/fleet/trajets/compatibles/",
            {"ville_depart": "Monastir", "ville_arrivee": "Tunis", "poids_kg": 25},
        )
        assert reponse.status_code == 200
        assert reponse.data["count"] == 1

    def test_compatibles_exclut_vehicule_non_conforme(self, pme, trajet):
        Vehicule.objects.filter(pk=trajet.vehicule_id).update(conforme=False, statut=Vehicule.Statut.NON_CONFORME)
        reponse = client_api(pme).get("/api/fleet/trajets/compatibles/", {"ville_depart": "Monastir"})
        assert reponse.data["count"] == 0

    def test_compatibles_filtre_ville_sans_resultat(self, pme, trajet):
        reponse = client_api(pme).get("/api/fleet/trajets/compatibles/", {"ville_depart": "Gabès"})
        assert reponse.data["count"] == 0

    def test_transporteur_ne_peut_pas_utiliser_compatibles(self, transporteur):
        reponse = client_api(transporteur).get("/api/fleet/trajets/compatibles/")
        assert reponse.status_code == 403

    def test_pme_recherche_via_query_compatible(self, pme, trajet):
        reponse = client_api(pme).get("/api/fleet/trajets/", {"compatible": "Monastir", "poids_kg": 25})
        assert reponse.status_code == 200
        assert reponse.data["count"] == 1


@pytest.mark.django_db
class TestFacteursEmissionAPI:
    def test_admin_crud(self, admin_user):
        client = client_api(admin_user)
        reponse = client.post(
            "/api/fleet/facteurs-emission/", {"type_vehicule": "CAMION", "kg_co2_par_km": "0.31"}, format="json"
        )
        assert reponse.status_code == 201
        assert FacteurEmission.objects.filter(type_vehicule="CAMION").exists()

    def test_transporteur_refuse(self, transporteur):
        reponse = client_api(transporteur).get("/api/fleet/facteurs-emission/")
        assert reponse.status_code == 403

    def test_admin_alias_api_admin(self, admin_user):
        reponse = client_api(admin_user).get("/api/admin/facteurs-emission/")
        assert reponse.status_code == 200
        assert "results" in reponse.data


@pytest.mark.django_db
class TestImpactAPI:
    def test_bilan_impact(self, transporteur, trajet):
        trajet.statut = Trajet.Statut.TERMINE
        trajet.co2_kg = 50.0
        trajet.save()
        reponse = client_api(transporteur).get(f"/api/fleet/vehicules/{trajet.vehicule_id}/impact/")
        assert reponse.status_code == 200
        assert reponse.data["co2_total_kg"] == 50.0

    def test_certificat_pdf(self, transporteur, trajet):
        trajet.statut = Trajet.Statut.TERMINE
        trajet.save()
        reponse = client_api(transporteur).get(f"/api/fleet/vehicules/{trajet.vehicule_id}/certificat/")
        assert reponse.status_code == 200
        assert reponse["Content-Type"] == "application/pdf"
