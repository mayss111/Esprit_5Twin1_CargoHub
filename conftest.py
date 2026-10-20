"""Données de test partagées par toute l'équipe (fixtures pytest)."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.accounts.models import ProfilPME, ProfilTransporteur, Utilisateur
from apps.core.roles import Role
from apps.fleet.models import Trajet, Vehicule
from apps.shipments.models import Adresse, ArticleExpedie, Expedition


@pytest.fixture
def pme(db):
    user = Utilisateur.objects.create_user("pme@test.tn", "motdepasse123", role=Role.PME, first_name="Sami")
    ProfilPME.objects.create(utilisateur=user, raison_sociale="Atelier Sami")
    return user


@pytest.fixture
def transporteur(db):
    user = Utilisateur.objects.create_user("karim@test.tn", "motdepasse123", role=Role.TRANSPORTEUR, first_name="Karim")
    ProfilTransporteur.objects.create(utilisateur=user, statut_validation=ProfilTransporteur.Statut.VALIDE)
    return user


@pytest.fixture
def admin_user(db):
    return Utilisateur.objects.create_superuser("admin@test.tn", "motdepasse123")


@pytest.fixture
def vehicule(transporteur):
    return Vehicule.objects.create(
        transporteur=transporteur,
        type=Vehicule.Type.CAMION,
        immatriculation="123 TU 4567",
        capacite_kg=3000,
        capacite_m3=Decimal("20"),
    )


@pytest.fixture
def trajet(transporteur, vehicule):
    return Trajet.objects.create(
        transporteur=transporteur,
        vehicule=vehicule,
        ville_depart="Monastir",
        ville_arrivee="Tunis",
        date_depart=timezone.now() + timedelta(days=2),
        capacite_dispo_kg=Decimal("1000"),
        capacite_dispo_m3=Decimal("8"),
        prix_indicatif=Decimal("85"),
        distance_km=160,
    )


@pytest.fixture
def expedition(pme):
    exp = Expedition.objects.create(
        pme=pme,
        adresse_depart=Adresse.objects.create(ligne="Zone industrielle", ville="Monastir"),
        adresse_arrivee=Adresse.objects.create(ligne="Rue de Marseille", ville="Tunis"),
        date_souhaitee=(timezone.now() + timedelta(days=2)).date(),
        statut=Expedition.Statut.PUBLIEE,
    )
    ArticleExpedie.objects.create(
        expedition=exp,
        designation="Cartons de vêtements",
        quantite=12,
        poids_kg=Decimal("25"),
        volume_m3=Decimal("0.15"),
        type_marchandise=ArticleExpedie.Type.TEXTILE,
    )
    return exp
