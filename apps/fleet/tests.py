"""Tests unitaires du module Flotte — modèles, conformité, CO₂, est_compatible."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.utils import timezone

from apps.accounts.models import Utilisateur
from apps.core.roles import Role
from apps.fleet import services
from apps.fleet.ai import recommander_vehicules
from apps.fleet.models import DocumentVehicule, FacteurEmission, Trajet, Vehicule
from apps.fleet.upload_validation import erreur_fichier_vehicule

AUJOURDHUI = timezone.now()


@pytest.mark.django_db
class TestVehicule:
    def test_vehicule_actif_par_defaut(self, vehicule):
        assert vehicule.statut == Vehicule.Statut.ACTIF
        assert vehicule.peut_publier_trajet()

    def test_document_expire_rend_non_conforme(self, vehicule):
        DocumentVehicule.objects.create(
            type=DocumentVehicule.Type.ASSURANCE,
            vehicule=vehicule,
            fichier="assurance.pdf",
            date_expiration=timezone.localdate() - timedelta(days=1),
        )
        assert vehicule.est_non_conforme()
        statut = vehicule.recalculer_conformite()
        assert statut == Vehicule.Statut.NON_CONFORME
        assert not vehicule.peut_publier_trajet()
        assert "Assurance expiré" in vehicule.motif_non_conformite

    def test_reactivation_quand_document_renouvele(self, vehicule):
        vehicule.statut = Vehicule.Statut.NON_CONFORME
        vehicule.conforme = False
        vehicule.save()
        assert vehicule.recalculer_conformite() == Vehicule.Statut.ACTIF

    def test_controle_technique_expire(self, vehicule):
        vehicule.controles.create(
            date_controle=timezone.localdate() - timedelta(days=400),
            date_expiration=timezone.localdate() - timedelta(days=35),
            favorable=True,
        )
        assert vehicule.est_non_conforme()


@pytest.mark.django_db
class TestTrajet:
    def test_date_passee_invalide(self, vehicule):
        trajet = Trajet(
            transporteur=vehicule.transporteur,
            vehicule=vehicule,
            ville_depart="Sousse",
            ville_arrivee="Tunis",
            date_depart=AUJOURDHUI - timedelta(days=1),
            capacite_dispo_kg=Decimal("100"),
            capacite_dispo_m3=Decimal("1"),
        )
        with pytest.raises(ValidationError):
            trajet.full_clean()

    def test_capacite_depasse_vehicule(self, vehicule):
        trajet = Trajet(
            transporteur=vehicule.transporteur,
            vehicule=vehicule,
            ville_depart="Sousse",
            ville_arrivee="Tunis",
            date_depart=AUJOURDHUI + timedelta(days=1),
            capacite_dispo_kg=Decimal("999999"),
            capacite_dispo_m3=Decimal("1"),
        )
        with pytest.raises(ValidationError):
            trajet.full_clean()

    def test_reserver_et_liberer_capacite(self, trajet):
        initial = trajet.capacite_dispo_kg
        trajet.reserver_capacite(Decimal("400"), Decimal("2"))
        trajet.refresh_from_db()
        assert trajet.capacite_dispo_kg == initial - 400
        trajet.liberer_capacite(Decimal("400"), Decimal("2"))
        trajet.refresh_from_db()
        assert trajet.capacite_dispo_kg == initial

    def test_surbooking_refuse(self, trajet):
        with pytest.raises(ValueError):
            trajet.reserver_capacite(Decimal("50000"), Decimal("1"))

    def test_statut_complet_quand_plus_de_place(self, trajet):
        trajet.capacite_dispo_m3 = Decimal("2")
        trajet.reserver_capacite(Decimal("1000"), Decimal("2"))
        trajet.refresh_from_db()
        assert trajet.statut == Trajet.Statut.COMPLET

    def test_taux_remplissage(self, trajet):
        assert trajet.taux_remplissage == 0
        trajet.capacite_totale_kg = Decimal("1000")
        trajet.capacite_reservee_kg  # noqa: B018 — property déclenche le calcul
        trajet._capacite_reservee_kg = None


@pytest.mark.django_db
class TestEstCompatible:
    def test_trajet_compatible(self, trajet, expedition):
        assert trajet.est_compatible(expedition) is True

    def test_ville_differente(self, trajet, expedition):
        trajet.ville_arrivee = "Sfax"
        assert trajet.est_compatible(expedition) is False

    def test_trajet_annule(self, trajet, expedition):
        trajet.statut = Trajet.Statut.ANNULE
        assert trajet.est_compatible(expedition) is False

    def test_date_depart_passee(self, trajet, expedition):
        trajet.date_depart = AUJOURDHUI - timedelta(days=1)
        assert trajet.est_compatible(expedition) is False

    def test_poids_trop_lourd(self, trajet, expedition):
        trajet.capacite_dispo_kg = Decimal("1")
        assert trajet.est_compatible(expedition) is False

    def test_vehicule_non_conforme(self, trajet, expedition):
        trajet.vehicule.statut = Vehicule.Statut.NON_CONFORME
        assert trajet.est_compatible(expedition) is False

    def test_service_trajets_compatibles(self, trajet, expedition):
        assert trajet in services.trajets_compatibles(expedition)


@pytest.mark.django_db
class TestCO2:
    def test_facteur_par_defaut(self, db):
        facteur = FacteurEmission.pour(Vehicule.Type.CAMION)
        assert facteur == Decimal("0.2500")

    def test_facteur_administrable(self, db):
        FacteurEmission.objects.create(type_vehicule=Vehicule.Type.CAMION, kg_co2_par_km=Decimal("0.3100"))
        assert FacteurEmission.pour(Vehicule.Type.CAMION) == Decimal("0.3100")

    def test_calcul_co2(self, trajet):
        trajet.capacite_totale_kg = Decimal("3000")
        trajet.distance_km = 100
        # 100 km × 0.25 kg/km × (1000/3000 charge) = 8.33 kg
        assert services.calculer_co2_trajet(trajet, 1000) == pytest.approx(8.33, abs=0.01)

    def test_charge_nulle(self, trajet):
        trajet.distance_km = 100
        assert services.calculer_co2_trajet(trajet, 0) == 0

    def test_bilan_co2(self, trajet):
        trajet.statut = Trajet.Statut.TERMINE
        trajet.co2_kg = 250.0
        trajet.save()
        bilan = services.bilan_co2(trajet.transporteur)
        assert bilan["nb_trajets"] == 1
        assert bilan["co2_total_kg"] == 250.0
        assert bilan["points_eco"] == 2

    def test_certificat_vert_pdf(self, trajet):
        trajet.statut = Trajet.Statut.TERMINE
        trajet.date_depart = timezone.now() - timedelta(days=1)
        trajet.co2_kg = 120.0
        trajet.save()
        contenu, bilan = services.generer_certificat_vert(
            trajet.transporteur, timezone.localdate() - timedelta(days=30), timezone.localdate()
        )
        assert contenu.startswith(b"%PDF")
        assert bilan["nb_trajets"] == 1


@pytest.mark.django_db
class TestPlanificateurIA:
    def test_classe_flotte_et_exclut_vehicules_d_autrui(self, transporteur, vehicule):
        grand = Vehicule.objects.create(
            transporteur=transporteur,
            type=Vehicule.Type.SEMI_REMORQUE,
            immatriculation="LARGE 01",
            capacite_kg=20000,
            capacite_m3=Decimal("100"),
        )
        autre = Utilisateur.objects.create_user("autre-planner@test.tn", "motdepasse123", role=Role.TRANSPORTEUR)
        Vehicule.objects.create(
            transporteur=autre,
            type=Vehicule.Type.CAMION,
            immatriculation="OTHER 01",
            capacite_kg=3000,
            capacite_m3=Decimal("20"),
        )

        resultat = recommander_vehicules(
            transporteur,
            poids_kg=2400,
            volume_m3=16,
            distance_km=100,
            date_depart=timezone.localdate() + timedelta(days=2),
        )

        assert [item["vehicule"].pk for item in resultat["resultats"]] == [vehicule.pk, grand.pk]
        assert resultat["resultats"][0]["score"] > resultat["resultats"][1]["score"]

    def test_aucun_vehicule_quand_charge_trop_lourde(self, transporteur, vehicule):
        resultat = recommander_vehicules(
            transporteur,
            poids_kg=vehicule.capacite_kg + 1,
            volume_m3=1,
            distance_km=50,
            date_depart=timezone.localdate() + timedelta(days=1),
        )
        assert resultat["resultats"] == []
        assert "Aucun véhicule" in resultat["message"]


def test_validation_signature_document_vehicule():
    valide = SimpleUploadedFile("assurance.pdf", b"%PDF-1.7 contenu", content_type="application/pdf")
    invalide = SimpleUploadedFile("assurance.pdf", b"pas un pdf", content_type="application/pdf")
    assert erreur_fichier_vehicule(valide) is None
    assert "ne correspond pas" in erreur_fichier_vehicule(invalide)


@pytest.mark.django_db
class TestVuesTransporteur:
    @pytest.fixture(autouse=True)
    def static_storage_without_manifest(self, settings):
        settings.STORAGES["staticfiles"] = {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        }

    def test_pme_refusee_sur_page_flotte(self, pme):
        client = Client()
        client.force_login(pme)
        assert client.get("/flotte/").status_code == 403

    def test_transporteur_ne_peut_pas_modifier_le_trajet_d_autrui(self, trajet):
        autre = Utilisateur.objects.create_user("autre-view@test.tn", "motdepasse123", role=Role.TRANSPORTEUR)
        client = Client()
        client.force_login(autre)
        reponse = client.get(f"/flotte/trajets/{trajet.pk}/modifier/")
        assert reponse.status_code == 404

    def test_vehicule_lie_a_un_trajet_ne_provoque_pas_erreur_serveur(self, transporteur, vehicule):
        trajet = Trajet.objects.create(
            transporteur=transporteur,
            vehicule=vehicule,
            ville_depart="Sousse",
            ville_arrivee="Tunis",
            date_depart=timezone.now() + timedelta(days=2),
            capacite_dispo_kg=Decimal("1000"),
            capacite_dispo_m3=Decimal("8"),
        )
        client = Client()
        client.force_login(transporteur)
        reponse = client.post(f"/flotte/vehicules/{vehicule.pk}/supprimer/")
        assert reponse.status_code == 302
        assert Trajet.objects.filter(pk=trajet.pk).exists()
        assert Vehicule.objects.filter(pk=vehicule.pk).exists()
