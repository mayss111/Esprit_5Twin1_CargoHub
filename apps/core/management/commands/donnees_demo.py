"""
python manage.py donnees_demo

Crée les mêmes données de démonstration chez tout le monde.
Mot de passe de tous les comptes : cargohub2026
"""

from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import ProfilPME, ProfilTransporteur, Utilisateur
from apps.bookings import services
from apps.bookings.models import Reservation
from apps.core.roles import Role
from apps.fleet.models import Trajet, Vehicule
from apps.shipments.models import Adresse, ArticleExpedie, Expedition
from apps.warehouses.models import Entrepot

MDP = "cargohub2026"


class Command(BaseCommand):
    help = "Crée des données de démonstration (admin, PME, transporteurs, trajets, réservations)."

    @transaction.atomic
    def handle(self, *args, **options):
        if Utilisateur.objects.filter(email="admin@cargohub.tn").exists():
            self.stdout.write(self.style.WARNING("Les données de démo existent déjà."))
            return

        Utilisateur.objects.create_superuser("admin@cargohub.tn", MDP, first_name="Admin")

        pme = Utilisateur.objects.create_user("sami@atelier.tn", MDP, role=Role.PME, first_name="Sami")
        ProfilPME.objects.create(utilisateur=pme, raison_sociale="Atelier Sami Textile", ville="Monastir")

        karim = Utilisateur.objects.create_user("karim@transport.tn", MDP, role=Role.TRANSPORTEUR, first_name="Karim")
        ProfilTransporteur.objects.create(utilisateur=karim, statut_validation=ProfilTransporteur.Statut.VALIDE)
        camion = Vehicule.objects.create(
            transporteur=karim,
            type=Vehicule.Type.CAMION,
            immatriculation="214 TU 3381",
            capacite_kg=3000,
            capacite_m3=Decimal("22"),
        )

        demain = timezone.now() + timedelta(days=1)
        trajet = Trajet.objects.create(
            transporteur=karim,
            vehicule=camion,
            ville_depart="Sfax",
            ville_arrivee="Tunis",
            date_depart=demain,
            capacite_dispo_kg=Decimal("1000"),
            capacite_dispo_m3=Decimal("8"),
            prix_indicatif=Decimal("85"),
            distance_km=270,
            recurrent=True,
        )
        trajet.etapes.create(ville="Sousse", ordre=1)
        trajet.etapes.create(ville="Monastir", ordre=2)

        expedition = Expedition.objects.create(
            pme=pme,
            adresse_depart=Adresse.objects.create(ligne="Zone industrielle", ville="Monastir"),
            adresse_arrivee=Adresse.objects.create(ligne="Rue de Marseille", ville="Tunis"),
            date_souhaitee=demain.date(),
            statut=Expedition.Statut.PUBLIEE,
            prix_estime=Decimal("85"),
        )
        ArticleExpedie.objects.create(
            expedition=expedition,
            designation="Cartons de vêtements",
            quantite=12,
            poids_kg=Decimal("25"),
            volume_m3=Decimal("0.15"),
            type_marchandise=ArticleExpedie.Type.TEXTILE,
        )
        reservation = services.reserver(expedition, trajet)
        services.changer_statut(reservation, Reservation.Statut.ACCEPTEE, par=karim)

        Entrepot.objects.create(nom="Relais Monastir Centre", adresse="Avenue Habib Bourguiba", ville="Monastir")
        Entrepot.objects.create(nom="Relais Sfax Port", adresse="Route de la Corniche", ville="Sfax")

        self.stdout.write(
            self.style.SUCCESS(
                f"Données créées (mot de passe : {MDP}) : admin@cargohub.tn, sami@atelier.tn, karim@transport.tn"
            )
        )
