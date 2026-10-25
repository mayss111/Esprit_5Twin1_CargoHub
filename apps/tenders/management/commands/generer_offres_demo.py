"""
python manage.py generer_offres_demo [--nombre 60]

Crée un historique réaliste d'offres RETENUES (appels attribués, transports terminés) pour que
la suggestion de prix du M4 utilise vraiment la régression pendant la démo (il en faut au moins 10).
Les données appartiennent à deux comptes inactifs dédiés : elles n'apparaissent pas chez Sami ou Karim.
Idempotent : relancer la commande ne crée que les offres manquantes.
"""

import random
from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import ProfilPME, ProfilTransporteur, Utilisateur
from apps.core.roles import Role
from apps.fleet.models import Trajet, Vehicule
from apps.shipments.models import Adresse, ArticleExpedie, Expedition
from apps.tenders.models import AppelOffre, Offre

MARQUE = "[démo IA]"

# (départ, arrivée, distance routière approximative en km)
LIAISONS = [
    ("Tunis", "Sfax", 270),
    ("Tunis", "Sousse", 140),
    ("Monastir", "Tunis", 160),
    ("Sfax", "Gabès", 137),
    ("Bizerte", "Tunis", 65),
    ("Nabeul", "Kairouan", 115),
    ("Tunis", "Tozeur", 430),
    ("Sousse", "Gafsa", 270),
    ("Tunis", "Médenine", 470),
    ("Béja", "Tunis", 105),
    ("Kairouan", "Sfax", 135),
    ("Tunis", "Jendouba", 155),
]


def prix_realiste(distance_km, poids_kg, hasard):
    """Même logique qu'un transporteur : fixe + distance × tonnes + usure, avec la variation d'une négociation."""
    return max(30.0, 25 + 0.32 * distance_km * poids_kg / 1000 + 0.04 * distance_km + hasard.gauss(0, 10))


class Command(BaseCommand):
    help = "Crée des offres retenues réalistes (historique d'entraînement de la suggestion de prix)."

    def add_arguments(self, parser):
        parser.add_argument("--nombre", type=int, default=60)

    @transaction.atomic
    def handle(self, *args, nombre, **options):
        existantes = Offre.objects.filter(statut=Offre.Statut.RETENUE, message__startswith=MARQUE).count()
        if existantes >= nombre:
            self.stdout.write(f"{existantes} offres de démonstration déjà présentes : rien à faire.")
            return

        pme = self.compte("historique.pme@cargohub.tn", Role.PME, "Historique")
        ProfilPME.objects.get_or_create(utilisateur=pme, defaults={"raison_sociale": "PME historique (démo IA)"})
        transporteur = self.compte("historique.transport@cargohub.tn", Role.TRANSPORTEUR, "Historique")
        ProfilTransporteur.objects.get_or_create(
            utilisateur=transporteur, defaults={"statut_validation": ProfilTransporteur.Statut.VALIDE}
        )
        vehicule, _ = Vehicule.objects.get_or_create(
            immatriculation="DEMO IA 0001",
            defaults={
                "transporteur": transporteur,
                "type": Vehicule.Type.SEMI_REMORQUE,
                "capacite_kg": 20000,
                "capacite_m3": Decimal("80"),
            },
        )

        hasard = random.Random(2026 + existantes)
        for _ in range(existantes, nombre):
            depart, arrivee, km = hasard.choice(LIAISONS)
            distance = round(km * hasard.uniform(0.95, 1.08), 1)
            poids = round(hasard.uniform(80, 4500), 2)
            date = timezone.now() - timedelta(days=hasard.randint(5, 300))
            prix = Decimal(prix_realiste(distance, poids, hasard)).quantize(Decimal("0.01"))

            expedition = Expedition.objects.create(
                pme=pme,
                adresse_depart=Adresse.objects.create(ligne="Zone industrielle", ville=depart),
                adresse_arrivee=Adresse.objects.create(ligne="Centre-ville", ville=arrivee),
                date_souhaitee=date.date(),
                statut=Expedition.Statut.LIVREE,
                description=MARQUE,
            )
            ArticleExpedie.objects.create(
                expedition=expedition,
                designation="Marchandise diverse",
                quantite=1,
                poids_kg=Decimal(str(poids)),
                volume_m3=Decimal(str(round(poids / 250, 3))),
            )
            trajet = Trajet.objects.create(
                transporteur=transporteur,
                vehicule=vehicule,
                ville_depart=depart,
                ville_arrivee=arrivee,
                date_depart=date,
                capacite_dispo_kg=Decimal("0"),
                capacite_dispo_m3=Decimal("0"),
                distance_km=distance,
                statut=Trajet.Statut.TERMINE,
            )
            appel = AppelOffre.objects.create(
                expedition=expedition,
                date_cloture=date - timedelta(days=2),
                prix_max=(prix * Decimal("1.3")).quantize(Decimal("1")),
                statut=AppelOffre.Statut.ATTRIBUE,
            )
            Offre.objects.create(
                appel=appel,
                transporteur=transporteur,
                trajet=trajet,
                prix=prix,
                message=f"{MARQUE} offre retenue de l’historique",
                statut=Offre.Statut.RETENUE,
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"{nombre - existantes} offres retenues créées ({nombre} au total) : la régression est active."
            )
        )

    def compte(self, email, role, prenom):
        user, cree = Utilisateur.objects.get_or_create(
            email=email, defaults={"role": role, "first_name": prenom, "is_active": False}
        )
        if cree:
            user.set_unusable_password()  # compte technique : personne ne peut s'y connecter
            user.save(update_fields=["password"])
        return user
