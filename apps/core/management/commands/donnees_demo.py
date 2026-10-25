"""
python manage.py donnees_demo

Crée les mêmes données de démonstration chez tout le monde, dont le scénario de soutenance du M4
(appel d’offres avec 2 offres et des avis). Peut être relancée sans créer de doublon.
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
from apps.tenders.models import AppelOffre, Offre
from apps.tracking.models import Avis
from apps.warehouses.models import Entrepot

MDP = "cargohub2026"
SOUTENANCE = "[démo soutenance]"  # repère les données du scénario, pour ne jamais les créer deux fois


class Command(BaseCommand):
    help = "Crée des données de démonstration (admin, PME, transporteurs, trajets, réservations)."

    @transaction.atomic
    def handle(self, *args, **options):
        if Utilisateur.objects.filter(email="admin@cargohub.tn").exists():
            self.stdout.write(self.style.WARNING("Les données de base existent déjà."))
        else:
            self.donnees_de_base()
        self.scenario_soutenance()

    def donnees_de_base(self):
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
            date_arrivee=(demain + timedelta(days=1)).date(),
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

    # ---------------------------------------------------------------- scénario de soutenance (M4)

    def scenario_soutenance(self):
        """
        Idempotent : peut être relancé (par exemple la veille de la soutenance) sans créer de doublon.
        Les dates sont recalées à J+7 tant que l'appel d'offres n'a pas été attribué.
        """
        sami = Utilisateur.objects.get(email="sami@atelier.tn")
        karim = Utilisateur.objects.get(email="karim@transport.tn")
        camion_karim = Vehicule.objects.filter(transporteur=karim).first()
        mohamed = self.transporteur("mohamed@transport.tn", "Mohamed")
        camion_mohamed, _ = Vehicule.objects.get_or_create(
            immatriculation="318 TU 7720",
            defaults={
                "transporteur": mohamed,
                "type": Vehicule.Type.CAMION,
                "capacite_kg": 3500,
                "capacite_m3": Decimal("20"),
            },
        )

        depart = (timezone.localtime() + timedelta(days=7)).replace(hour=8, minute=0, second=0, microsecond=0)
        expedition = Expedition.objects.filter(pme=sami, description=SOUTENANCE).first()
        if expedition is None:
            expedition = Expedition.objects.create(
                pme=sami,
                adresse_depart=Adresse.objects.create(ligne="Zone industrielle", ville="Monastir"),
                adresse_arrivee=Adresse.objects.create(ligne="Avenue de Carthage", ville="Tunis"),
                date_souhaitee=depart.date(),
                date_arrivee=(depart + timedelta(days=1)).date(),
                statut=Expedition.Statut.PUBLIEE,
                description=SOUTENANCE,
            )
            ArticleExpedie.objects.create(
                expedition=expedition,
                designation="Rouleaux de tissu",
                quantite=12,
                poids_kg=Decimal("25"),  # 300 kg
                volume_m3=Decimal("0.2"),
                type_marchandise=ArticleExpedie.Type.TEXTILE,
            )

        appel, _ = AppelOffre.objects.get_or_create(
            expedition=expedition, defaults={"date_cloture": depart - timedelta(days=2), "prix_max": Decimal("150")}
        )
        if appel.statut == AppelOffre.Statut.OUVERT:  # on recale les dates tant que rien n'a été attribué
            Expedition.objects.filter(pk=expedition.pk).update(
                date_souhaitee=depart.date(), date_arrivee=(depart + timedelta(days=1)).date()
            )
            AppelOffre.objects.filter(pk=appel.pk).update(date_cloture=depart - timedelta(days=2))
            # Mohamed : direct et moins cher, mais moins bien noté ; Karim : plus cher, via Monastir, très bien noté.
            self.offre_demo(
                appel, mohamed, camion_mohamed, "Monastir", [], depart, 160, "95", "Trajet direct, départ 8 h."
            )
            self.offre_demo(
                appel,
                karim,
                camion_karim,
                "Sfax",
                ["Monastir", "Sousse"],
                depart - timedelta(hours=2),
                270,
                "110",
                "Je passe par Monastir, chargement soigné.",
            )
            appel.effacer_recommandation()

        self.avis_passes(sami, karim, camion_karim, [5, 5, 4], "Livraison à l’heure, très soigneux.")
        self.avis_passes(sami, mohamed, camion_mohamed, [3, 2], "Retard à la livraison, cartons abîmés.")
        self.stdout.write(
            self.style.SUCCESS(
                f"Scénario de soutenance prêt : appel d’offres #{appel.pk} (Monastir - Tunis, 300 kg) avec les offres "
                f"de Mohamed (95 DT) et Karim (110 DT). Nouveau compte : mohamed@transport.tn / {MDP}"
            )
        )

    def offre_demo(self, appel, transporteur, camion, ville_depart, etapes, date, distance, prix, message):
        """Le trajet de démo est retrouvé par son offre : aucun risque de confondre avec un trajet créé à la main."""
        offre = Offre.objects.filter(appel=appel, transporteur=transporteur).select_related("trajet").first()
        trajet = offre.trajet if offre and offre.trajet else Trajet(transporteur=transporteur)
        trajet.vehicule, trajet.ville_depart, trajet.ville_arrivee = camion, ville_depart, "Tunis"
        trajet.date_depart, trajet.distance_km, trajet.prix_indicatif = date, distance, Decimal(prix)
        trajet.capacite_dispo_kg, trajet.capacite_dispo_m3 = Decimal("1500"), Decimal("10")
        trajet.statut = Trajet.Statut.OUVERT
        trajet.save()
        for ordre, ville in enumerate(etapes, start=1):
            trajet.etapes.update_or_create(ordre=ordre, defaults={"ville": ville})
        Offre.objects.update_or_create(
            appel=appel,
            transporteur=transporteur,
            defaults={"trajet": trajet, "prix": Decimal(prix), "message": message, "statut": Offre.Statut.PROPOSEE},
        )

    def transporteur(self, email, prenom):
        user, cree = Utilisateur.objects.get_or_create(
            email=email, defaults={"role": Role.TRANSPORTEUR, "first_name": prenom, "is_active": True}
        )
        if cree:
            user.set_password(MDP)
            user.save(update_fields=["password"])
        ProfilTransporteur.objects.get_or_create(
            utilisateur=user, defaults={"statut_validation": ProfilTransporteur.Statut.VALIDE}
        )
        return user

    def avis_passes(self, pme, transporteur, camion, notes, commentaire):
        """Anciens transports livrés, chacun avec un avis de Sami (un avis par réservation)."""
        if Avis.objects.filter(auteur=pme, cible=transporteur, commentaire__startswith=SOUTENANCE).exists():
            return
        for i, note in enumerate(notes, start=1):
            date = timezone.now() - timedelta(days=20 * i)
            expedition = Expedition.objects.create(
                pme=pme,
                adresse_depart=Adresse.objects.create(ligne="Zone industrielle", ville="Monastir"),
                adresse_arrivee=Adresse.objects.create(ligne="Centre-ville", ville="Tunis"),
                date_souhaitee=date.date(),
                date_arrivee=(date + timedelta(days=1)).date(),
                statut=Expedition.Statut.LIVREE,
                description=f"{SOUTENANCE} historique",
            )
            ArticleExpedie.objects.create(
                expedition=expedition,
                designation="Cartons",
                quantite=4,
                poids_kg=Decimal("25"),
                volume_m3=Decimal("0.1"),
            )
            trajet = Trajet.objects.create(
                transporteur=transporteur,
                vehicule=camion,
                ville_depart="Monastir",
                ville_arrivee="Tunis",
                date_depart=date,
                capacite_dispo_kg=Decimal("0"),
                capacite_dispo_m3=Decimal("0"),
                distance_km=160,
                statut=Trajet.Statut.TERMINE,
            )
            reservation = Reservation.objects.create(
                expedition=expedition, trajet=trajet, statut=Reservation.Statut.LIVREE, prix_convenu=Decimal("90")
            )
            Avis.objects.create(
                reservation=reservation,
                auteur=pme,
                cible=transporteur,
                note=note,
                commentaire=f"{SOUTENANCE} {commentaire}",
            )
