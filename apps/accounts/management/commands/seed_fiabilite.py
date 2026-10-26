"""Crée un jeu de données local pour essayer le score de fiabilité."""

from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.accounts.models import ProfilPME, ProfilTransporteur, Utilisateur
from apps.bookings.models import Reservation
from apps.core.roles import Role
from apps.fleet.models import Trajet, Vehicule
from apps.insurance.models import Sinistre
from apps.reclamations.models import Reclamation
from apps.shipments.models import Adresse, ArticleExpedie, Expedition
from apps.tracking.models import Incident


def ajouter_livraison_demo(pme, transporteur, depart, arrivee, marqueur, immatriculation):
    """Ajoute une livraison clôturée pour un compte réel de développement."""
    vehicule, _ = Vehicule.objects.get_or_create(
        immatriculation=immatriculation,
        defaults={
            "transporteur": transporteur,
            "type": Vehicule.Type.CAMIONNETTE,
            "capacite_kg": 1500,
            "capacite_m3": Decimal("10"),
        },
    )
    trajet, _ = Trajet.objects.get_or_create(
        transporteur=transporteur,
        vehicule=vehicule,
        ville_depart="Monastir",
        ville_arrivee="Tunis",
        defaults={
            "date_depart": timezone.now() + timedelta(days=14),
            "capacite_dispo_kg": Decimal("1500"),
            "capacite_dispo_m3": Decimal("10"),
            "prix_indicatif": Decimal("90"),
            "distance_km": 160,
        },
    )
    expedition, _ = Expedition.objects.get_or_create(
        pme=pme,
        description=marqueur,
        defaults={
            "adresse_depart": depart,
            "adresse_arrivee": arrivee,
            "date_souhaitee": timezone.localdate() + timedelta(days=14),
            "date_arrivee": timezone.localdate() + timedelta(days=15),
            "statut": Expedition.Statut.LIVREE,
        },
    )
    reservation, _ = Reservation.objects.get_or_create(
        expedition=expedition,
        trajet=trajet,
        defaults={"statut": Reservation.Statut.LIVREE, "prix_convenu": Decimal("90")},
    )
    if reservation.statut != Reservation.Statut.LIVREE:
        reservation.statut = Reservation.Statut.LIVREE
        reservation.save(update_fields=["statut"])
    ArticleExpedie.objects.get_or_create(
        expedition=expedition,
        designation=f"Marchandise {marqueur}",
        defaults={"quantite": 1, "poids_kg": Decimal("5"), "volume_m3": Decimal("0.05")},
    )


class Command(BaseCommand):
    help = "Ajoute des données de démonstration pour le score de fiabilité."

    def handle(self, *args, **options):
        pme, _ = Utilisateur.objects.get_or_create(
            email="demo.pme@cargohub.test",
            defaults={"first_name": "PME", "last_name": "Démo", "role": Role.PME},
        )
        pme.role = Role.PME
        pme.set_password("DemoCargoHub2026!")
        pme.save(update_fields=["role", "password"])
        ProfilPME.objects.get_or_create(utilisateur=pme, defaults={"raison_sociale": "PME Démo CargoHub"})

        transporteur, _ = Utilisateur.objects.get_or_create(
            email="demo.transporteur@cargohub.test",
            defaults={"first_name": "Transporteur", "last_name": "Démo", "role": Role.TRANSPORTEUR},
        )
        transporteur.role = Role.TRANSPORTEUR
        transporteur.set_password("DemoCargoHub2026!")
        transporteur.save(update_fields=["role", "password"])
        ProfilTransporteur.objects.get_or_create(
            utilisateur=transporteur,
            defaults={"statut_validation": ProfilTransporteur.Statut.VALIDE},
        )

        vehicule, _ = Vehicule.objects.get_or_create(
            immatriculation="DEMO-100",
            defaults={
                "transporteur": transporteur,
                "type": Vehicule.Type.CAMION,
                "capacite_kg": 3000,
                "capacite_m3": Decimal("20"),
            },
        )
        trajet, _ = Trajet.objects.get_or_create(
            transporteur=transporteur,
            vehicule=vehicule,
            ville_depart="Monastir",
            ville_arrivee="Tunis",
            defaults={
                "date_depart": timezone.now() + timedelta(days=7),
                "capacite_dispo_kg": Decimal("3000"),
                "capacite_dispo_m3": Decimal("20"),
                "prix_indicatif": Decimal("120"),
                "distance_km": 160,
            },
        )
        depart = Adresse.objects.get_or_create(ligne="Zone industrielle", ville="Monastir")[0]
        arrivee = Adresse.objects.get_or_create(ligne="Centre logistique", ville="Tunis")[0]

        reservations = []
        for index, statut in enumerate(
            [
                Reservation.Statut.LIVREE,
                Reservation.Statut.LIVREE,
                Reservation.Statut.LIVREE,
                Reservation.Statut.ANNULEE,
            ],
            start=1,
        ):
            expedition, _ = Expedition.objects.get_or_create(
                pme=pme,
                description=f"DEMO_FIABILITE_{index}",
                defaults={
                    "adresse_depart": depart,
                    "adresse_arrivee": arrivee,
                    "date_souhaitee": timezone.localdate() + timedelta(days=index),
                    "date_arrivee": timezone.localdate() + timedelta(days=index + 1),
                    "statut": Expedition.Statut.LIVREE
                    if statut == Reservation.Statut.LIVREE
                    else Expedition.Statut.ANNULEE,
                },
            )
            reservation, _ = Reservation.objects.get_or_create(
                expedition=expedition,
                trajet=trajet,
                defaults={"statut": statut, "prix_convenu": Decimal("120")},
            )
            if reservation.statut != statut:
                reservation.statut = statut
                reservation.save(update_fields=["statut"])
            ArticleExpedie.objects.get_or_create(
                expedition=expedition,
                designation="Cartons de démonstration",
                defaults={"quantite": 1, "poids_kg": Decimal("10"), "volume_m3": Decimal("0.1")},
            )
            reservations.append(reservation)

        # Une livraison supplémentaire réservée uniquement au transporteur
        # rend les deux scores de démonstration volontairement différents.
        client_pme, _ = Utilisateur.objects.get_or_create(
            email="demo.client@cargohub.test",
            defaults={"first_name": "Client", "last_name": "Démo", "role": Role.PME},
        )
        client_pme.role = Role.PME
        client_pme.save(update_fields=["role"])
        ProfilPME.objects.get_or_create(utilisateur=client_pme, defaults={"raison_sociale": "Client Démo CargoHub"})
        expedition_transporteur, _ = Expedition.objects.get_or_create(
            pme=client_pme,
            description="DEMO_FIABILITE_TRANSPORTEUR",
            defaults={
                "adresse_depart": depart,
                "adresse_arrivee": arrivee,
                "date_souhaitee": timezone.localdate() + timedelta(days=10),
                "date_arrivee": timezone.localdate() + timedelta(days=11),
                "statut": Expedition.Statut.LIVREE,
            },
        )
        Reservation.objects.get_or_create(
            expedition=expedition_transporteur,
            trajet=trajet,
            defaults={"statut": Reservation.Statut.LIVREE, "prix_convenu": Decimal("120")},
        )
        ArticleExpedie.objects.get_or_create(
            expedition=expedition_transporteur,
            designation="Cartons supplémentaires de démonstration",
            defaults={"quantite": 1, "poids_kg": Decimal("8"), "volume_m3": Decimal("0.08")},
        )

        # Les comptes locaux utilisés pendant la démonstration reçoivent aussi
        # une livraison : Sami et Karim voient donc un score dès leur accueil.
        sami = Utilisateur.objects.filter(email="sami@atelier.tn", role=Role.PME).first()
        if sami:
            ajouter_livraison_demo(sami, transporteur, depart, arrivee, "DEMO_FIABILITE_SAMI", "DEMO-SAMI")
        karim = Utilisateur.objects.filter(email="karim@transport.tn", role=Role.TRANSPORTEUR).first()
        if karim:
            ajouter_livraison_demo(pme, karim, depart, arrivee, "DEMO_FIABILITE_KARIM", "DEMO-KARIM")

        Incident.objects.get_or_create(
            reservation=reservations[0],
            type=Incident.Type.RETARD,
            defaults={
                "declare_par": pme,
                "description": "DEMO_FIABILITE : retard résolu",
                "statut": Incident.Statut.RESOLU,
            },
        )
        expedition = reservations[0].expedition
        Reclamation.objects.get_or_create(
            expedition=expedition,
            titre="DEMO_FIABILITE : réclamation confirmée",
            defaults={
                "auteur": pme,
                "description": "Réclamation de démonstration résolue.",
                "type_reclamation": Reclamation.Type.RETARD,
                "statut": Reclamation.Statut.RESOLUE,
            },
        )
        Sinistre.objects.get_or_create(
            expedition=expedition,
            titre="DEMO_FIABILITE : sinistre imputable",
            defaults={
                "auteur": pme,
                "description": "Sinistre de démonstration accepté.",
                "type_sinistre": Sinistre.Type.DOMMAGE,
                "statut": Sinistre.Statut.ACCEPTE,
                "decision_admin": "Responsabilité établie pour la démonstration.",
            },
        )

        self.stdout.write(self.style.SUCCESS("Données de fiabilité ajoutées."))
        self.stdout.write("PME : demo.pme@cargohub.test / DemoCargoHub2026!")
        self.stdout.write("Transporteur : demo.transporteur@cargohub.test / DemoCargoHub2026!")
