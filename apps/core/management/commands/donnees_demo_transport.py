"""Alimente la flotte de démonstration avec trajets, entretiens et contrôles variés."""

from datetime import datetime, time, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.accounts.models import Utilisateur
from apps.fleet.models import Trajet, Vehicule
from apps.maintenance.models import ControleTechnique, DepenseVehicule, Entretien

VEHICULES = [
    ("DEMO-T-101", Vehicule.Type.CAMIONNETTE, 1500, "6.00", Vehicule.Statut.ACTIF),
    ("DEMO-T-102", Vehicule.Type.CAMION, 5000, "22.00", Vehicule.Statut.ACTIF),
    ("DEMO-T-103", Vehicule.Type.SEMI_REMORQUE, 18000, "82.00", Vehicule.Statut.EN_MAINTENANCE),
    ("DEMO-T-104", Vehicule.Type.FRIGORIFIQUE, 8000, "35.00", Vehicule.Statut.NON_CONFORME),
    ("DEMO-T-105", Vehicule.Type.CAMION, 7500, "32.00", Vehicule.Statut.ACTIF),
    ("DEMO-T-106", Vehicule.Type.CAMIONNETTE, 2200, "9.00", Vehicule.Statut.ACTIF),
    ("DEMO-T-107", Vehicule.Type.SEMI_REMORQUE, 24000, "90.00", Vehicule.Statut.NON_CONFORME),
    ("DEMO-T-108", Vehicule.Type.FRIGORIFIQUE, 10000, "44.00", Vehicule.Statut.ACTIF),
]


class Command(BaseCommand):
    help = "Crée un scénario réexécutable de flotte, trajets, entretiens et contrôles techniques."

    def handle(self, *args, **options):
        try:
            transporteur = Utilisateur.objects.get(email="karim@transport.tn")
        except Utilisateur.DoesNotExist as exc:
            raise CommandError(
                "Créez d'abord les comptes de démonstration avec `python manage.py donnees_demo`."
            ) from exc

        aujourd_hui = timezone.localdate()
        vehicules = []
        for immatriculation, type_vehicule, capacite, volume, statut in VEHICULES:
            vehicule, _ = Vehicule.objects.update_or_create(
                immatriculation=immatriculation,
                defaults={
                    "transporteur": transporteur,
                    "type": type_vehicule,
                    "capacite_kg": capacite,
                    "capacite_m3": Decimal(volume),
                    "conforme": statut != Vehicule.Statut.NON_CONFORME,
                    "statut": statut,
                    "motif_non_conformite": ""
                    if statut != Vehicule.Statut.NON_CONFORME
                    else "Contrôle technique à vérifier",
                },
            )
            vehicules.append(vehicule)

            for n, (jours, km, cout, echeance) in enumerate(
                [(-270, 52000, "420.00", 180), (-180, 58500, "780.00", 90), (-90, 65300, "310.00", 30)],
                start=1,
            ):
                Entretien.objects.update_or_create(
                    vehicule=vehicule,
                    type=("Vidange", "Pneumatiques", "Freins")[n - 1],
                    date=aujourd_hui + timedelta(days=jours),
                    defaults={
                        "kilometrage": km + (n - 1) * (vehicules.index(vehicule) * 800),
                        "cout": Decimal(cout),
                        "prochaine_echeance": aujourd_hui + timedelta(days=echeance - vehicules.index(vehicule) * 12),
                    },
                )

            if statut == Vehicule.Statut.NON_CONFORME and immatriculation == "DEMO-T-104":
                date_controle = aujourd_hui - timedelta(days=370)
                date_expiration = aujourd_hui - timedelta(days=5)
                favorable = True
            elif statut == Vehicule.Statut.NON_CONFORME:
                date_controle = aujourd_hui - timedelta(days=5)
                date_expiration = aujourd_hui + timedelta(days=360)
                favorable = False
            else:
                date_controle = aujourd_hui - timedelta(days=30)
                date_expiration = aujourd_hui + timedelta(days=335)
                favorable = True
            ControleTechnique.objects.update_or_create(
                vehicule=vehicule,
                date_controle=date_controle,
                defaults={"date_expiration": date_expiration, "favorable": favorable},
            )

            for categorie, jours, montant in [
                (DepenseVehicule.Categorie.CARBURANT, -2, "185.50"),
                (DepenseVehicule.Categorie.PEAGE, -8, "42.00"),
                (DepenseVehicule.Categorie.REPARATION, -35, "260.00"),
            ]:
                DepenseVehicule.objects.update_or_create(
                    vehicule=vehicule,
                    categorie=categorie,
                    date=aujourd_hui + timedelta(days=jours),
                    defaults={"montant": Decimal(montant) + Decimal(vehicules.index(vehicule) * 5)},
                )

        trajets = [
            (0, "Tunis", "Sousse", 2, Trajet.Statut.OUVERT),
            (0, "Sousse", "Tunis", -7, Trajet.Statut.TERMINE),
            (1, "Sfax", "Tunis", -14, Trajet.Statut.TERMINE),
            (1, "Tunis", "Gabès", 0, Trajet.Statut.EN_COURS),
            (2, "Sousse", "Monastir", -3, Trajet.Statut.ANNULE),
            (3, "Tunis", "Bizerte", -21, Trajet.Statut.TERMINE),
            (4, "Sousse", "Tunis", 4, Trajet.Statut.OUVERT),
            (4, "Tunis", "Sfax", 0, Trajet.Statut.EN_COURS),
            (5, "Monastir", "Tunis", -30, Trajet.Statut.TERMINE),
            (6, "Sfax", "Gabès", 3, Trajet.Statut.ANNULE),
            (7, "Tunis", "Sousse", 5, Trajet.Statut.OUVERT),
            (7, "Gabès", "Tunis", -45, Trajet.Statut.TERMINE),
        ]
        for index, depart, arrivee, decalage, statut in trajets:
            vehicule = vehicules[index]
            capacite = Decimal(vehicule.capacite_kg)
            volume = vehicule.capacite_m3
            date_depart = timezone.make_aware(
                datetime.combine(aujourd_hui + timedelta(days=decalage), time(8))
            )
            Trajet.objects.update_or_create(
                vehicule=vehicule,
                ville_depart=depart,
                ville_arrivee=arrivee,
                date_depart=date_depart,
                defaults={
                    "transporteur": transporteur,
                    "capacite_dispo_kg": capacite / 2,
                    "capacite_dispo_m3": volume / 2,
                    "capacite_totale_kg": capacite,
                    "capacite_totale_m3": volume,
                    "prix_indicatif": Decimal("145.00") + Decimal(index * 20),
                    "distance_km": 120 + index * 35,
                    "statut": statut,
                    "co2_kg": round((120 + index * 35) * 0.25, 2),
                },
            )

        self.stdout.write(
            self.style.SUCCESS(
                "Scénario transport prêt : 8 véhicules (actifs, en maintenance et non conformes), "
                "12 trajets, 24 entretiens, 8 contrôles techniques et 24 dépenses."
            )
        )
