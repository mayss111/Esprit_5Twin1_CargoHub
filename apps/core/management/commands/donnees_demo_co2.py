"""Ajoute un jeu de validation réexécutable au bilan CO₂ de la flotte."""

from datetime import datetime, time, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.accounts.models import Utilisateur
from apps.bookings.models import Reservation
from apps.ecology.services import enregistrer_empreinte_reservation
from apps.fleet.models import FacteurEmission, Trajet, Vehicule
from apps.shipments.models import Adresse, ArticleExpedie, Expedition

FACTEURS = {
    Vehicule.Type.CAMIONNETTE: ("0.1800", 0.18),
    Vehicule.Type.CAMION: ("0.2500", 0.25),
    Vehicule.Type.SEMI_REMORQUE: ("0.4100", 0.41),
    Vehicule.Type.FRIGORIFIQUE: ("0.3300", 0.33),
}


class Command(BaseCommand):
    help = "Ajoute des véhicules, trajets terminés et une livraison pour valider les bilans CO₂."

    def handle(self, *args, **options):
        try:
            transporteur = Utilisateur.objects.get(email="karim@transport.tn")
            pme = Utilisateur.objects.get(email="sami@atelier.tn")
        except Utilisateur.DoesNotExist as exc:
            raise CommandError("Créez d'abord les comptes avec `python manage.py donnees_demo`.") from exc

        for type_vehicule, (facteur, _valeur) in FACTEURS.items():
            FacteurEmission.objects.update_or_create(
                type_vehicule=type_vehicule, defaults={"kg_co2_par_km": Decimal(facteur)}
            )

        configurations = [
            ("214 TU 3382", Vehicule.Type.CAMIONNETTE, 1500, "6.00"),
            ("214 TU 3383", Vehicule.Type.SEMI_REMORQUE, 18000, "82.00"),
            ("214 TU 3384", Vehicule.Type.FRIGORIFIQUE, 8000, "35.00"),
        ]
        fin = timezone.localdate() - timedelta(days=2)
        for index, (immatriculation, type_vehicule, capacite, volume) in enumerate(configurations):
            vehicule, _ = Vehicule.objects.update_or_create(
                immatriculation=immatriculation,
                defaults={
                    "transporteur": transporteur,
                    "type": type_vehicule,
                    "capacite_kg": capacite,
                    "capacite_m3": Decimal(volume),
                    "conforme": True,
                    "statut": Vehicule.Statut.ACTIF,
                    "motif_non_conformite": "",
                },
            )
            distance = 270 + index * 45
            Trajet.objects.update_or_create(
                vehicule=vehicule,
                ville_depart="Tunis",
                ville_arrivee="Sfax",
                distance_km=distance,
                defaults={
                    "transporteur": transporteur,
                    "date_depart": timezone.make_aware(datetime.combine(fin - timedelta(days=index), time(12))),
                    "capacite_dispo_kg": Decimal(capacite) * Decimal("0.5"),
                    "capacite_dispo_m3": Decimal(volume) * Decimal("0.5"),
                    "capacite_totale_kg": Decimal(capacite),
                    "capacite_totale_m3": Decimal(volume),
                    "distance_km": distance,
                    "statut": Trajet.Statut.TERMINE,
                    "co2_kg": round(distance * FACTEURS[type_vehicule][1] * 0.5, 2),
                },
            )

        semi = Vehicule.objects.get(immatriculation="214 TU 3383")
        Trajet.objects.update_or_create(
            vehicule=semi,
            ville_depart="Sousse",
            ville_arrivee="Tunis",
            distance_km=360,
            defaults={
                "transporteur": transporteur,
                "date_depart": timezone.make_aware(datetime.combine(fin - timedelta(days=5), time(12))),
                "capacite_dispo_kg": Decimal("9000"),
                "capacite_dispo_m3": Decimal("41"),
                "capacite_totale_kg": Decimal("18000"),
                "capacite_totale_m3": Decimal("82"),
                "distance_km": 360,
                "statut": Trajet.Statut.TERMINE,
                "co2_kg": round(360 * FACTEURS[Vehicule.Type.SEMI_REMORQUE][1] * 0.5, 2),
            },
        )

        trajet_demo = Trajet.objects.get(vehicule__immatriculation="214 TU 3382", distance_km=270)
        # Les adresses de démonstration ne sont pas uniques en base : reprendre la première
        # correspondance évite MultipleObjectsReturned après plusieurs exécutions de donnees_demo.
        depart = Adresse.objects.filter(ligne="Zone industrielle", ville="Monastir").order_by("pk").first()
        if depart is None:
            depart = Adresse.objects.create(ligne="Zone industrielle", ville="Monastir")
        arrivee = Adresse.objects.filter(ligne="Rue de Marseille", ville="Tunis").order_by("pk").first()
        if arrivee is None:
            arrivee = Adresse.objects.create(ligne="Rue de Marseille", ville="Tunis")
        expedition, _ = Expedition.objects.get_or_create(
            pme=pme,
            description="Expédition de démonstration pour valider le CO₂ économisé.",
            defaults={
                "adresse_depart": depart,
                "adresse_arrivee": arrivee,
                "date_souhaitee": trajet_demo.date_depart.date(),
                "date_arrivee": trajet_demo.date_depart.date() + timedelta(days=1),
                "statut": Expedition.Statut.LIVREE,
            },
        )
        ArticleExpedie.objects.get_or_create(
            expedition=expedition,
            designation="Cartons textiles partagés",
            defaults={
                "quantite": 12,
                "poids_kg": Decimal("25"),
                "volume_m3": Decimal("0.15"),
                "type_marchandise": ArticleExpedie.Type.TEXTILE,
            },
        )
        reservation, _ = Reservation.objects.update_or_create(
            expedition=expedition,
            trajet=trajet_demo,
            defaults={"statut": Reservation.Statut.LIVREE},
        )
        # Le seed initial crée certaines livraisons directement sans passer par le workflow
        # de changement de statut. Recalculer les empreintes rend le bilan de démo complet.
        livraisons = Reservation.objects.filter(
            statut=Reservation.Statut.LIVREE,
            expedition__pme=pme,
        ).select_related("expedition", "trajet__vehicule")
        for livraison in livraisons:
            enregistrer_empreinte_reservation(livraison)
        self.stdout.write(
            self.style.SUCCESS("Données CO2 prêtes : 3 véhicules, 4 trajets terminés et 1 livraison de démonstration.")
        )
