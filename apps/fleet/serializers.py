"""Serializers du module Flotte — validation serveur, messages en français."""

from django.db.models import Max
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied

from apps.core.roles import est_admin
from apps.maintenance.models import Entretien

from .models import DocumentVehicule, FacteurEmission, Trajet, Vehicule
from .upload_validation import erreur_fichier_vehicule


class DocumentVehiculeSerializer(serializers.ModelSerializer):
    class Meta:
        model = DocumentVehicule
        fields = ["id", "type", "fichier", "date_expiration"]
        read_only_fields = ["id"]

    def validate_fichier(self, fichier):
        erreur = erreur_fichier_vehicule(fichier)
        if erreur:
            raise serializers.ValidationError(erreur)
        return fichier

    def validate_date_expiration(self, valeur):
        if valeur <= timezone.localdate():
            raise serializers.ValidationError("La date d'expiration doit être dans le futur.")
        return valeur


class VehiculeSerializer(serializers.ModelSerializer):
    documents = DocumentVehiculeSerializer(many=True, read_only=True)
    statut = serializers.CharField(read_only=True)
    motif_non_conformite = serializers.CharField(read_only=True)

    class Meta:
        model = Vehicule
        fields = [
            "id",
            "type",
            "immatriculation",
            "capacite_kg",
            "capacite_m3",
            "statut",
            "conforme",
            "motif_non_conformite",
            "documents",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "conforme", "created_at", "updated_at"]

    def validate_immatriculation(self, valeur):
        return valeur.upper().strip()

    def validate(self, donnees):
        capacite_kg = donnees.get("capacite_kg", self.instance.capacite_kg if self.instance else 1)
        capacite_m3 = donnees.get("capacite_m3", self.instance.capacite_m3 if self.instance else 1)
        if capacite_kg < 1:
            raise serializers.ValidationError({"capacite_kg": "La capacité doit être d'au moins 1 kg."})
        if capacite_m3 <= 0:
            raise serializers.ValidationError({"capacite_m3": "La capacité doit être supérieure à 0 m³."})
        if self.instance:
            capacites_utilisees = self.instance.trajets.filter(
                statut__in=[Trajet.Statut.PUBLIE, Trajet.Statut.COMPLET, Trajet.Statut.EN_COURS]
            ).aggregate(poids=Max("capacite_totale_kg"), volume=Max("capacite_totale_m3"))
            erreurs = {}
            if capacites_utilisees["poids"] and capacite_kg < capacites_utilisees["poids"]:
                erreurs["capacite_kg"] = "La capacité ne peut pas être inférieure à celle d'un trajet actif."
            if capacites_utilisees["volume"] and capacite_m3 < capacites_utilisees["volume"]:
                erreurs["capacite_m3"] = "Le volume ne peut pas être inférieur à celui d'un trajet actif."
            if erreurs:
                raise serializers.ValidationError(erreurs)
        return donnees


class TrajetSerializer(serializers.ModelSerializer):
    vehicule_immatriculation = serializers.CharField(source="vehicule.immatriculation", read_only=True)
    taux_remplissage = serializers.FloatField(read_only=True)
    capacite_reservee_kg = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = Trajet
        fields = [
            "id",
            "vehicule",
            "vehicule_immatriculation",
            "ville_depart",
            "ville_arrivee",
            "date_depart",
            "capacite_dispo_kg",
            "capacite_dispo_m3",
            "capacite_totale_kg",
            "capacite_totale_m3",
            "prix_indicatif",
            "distance_km",
            "recurrent",
            "statut",
            "taux_remplissage",
            "capacite_reservee_kg",
            "co2_kg",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "statut", "created_at", "updated_at"]

    def validate_date_depart(self, valeur):
        if valeur <= timezone.now():
            raise serializers.ValidationError("La date de départ doit être dans le futur.")
        return valeur

    def validate(self, donnees):
        capacite_kg = donnees.get("capacite_dispo_kg", self.instance.capacite_dispo_kg if self.instance else None)
        capacite_m3 = donnees.get("capacite_dispo_m3", self.instance.capacite_dispo_m3 if self.instance else None)
        if capacite_kg is not None and capacite_kg <= 0:
            raise serializers.ValidationError({"capacite_dispo_kg": "La capacité disponible doit être supérieure à 0."})
        if capacite_m3 is not None and capacite_m3 <= 0:
            raise serializers.ValidationError({"capacite_dispo_m3": "La capacité disponible doit être supérieure à 0."})
        vehicule = donnees.get("vehicule") or (self.instance and self.instance.vehicule)
        request = self.context.get("request")
        if vehicule and request and not est_admin(request.user) and vehicule.transporteur_id != request.user.pk:
            raise PermissionDenied("Ce véhicule ne vous appartient pas.")
        if vehicule and not vehicule.peut_publier_trajet():
            raise serializers.ValidationError(
                f"Impossible de publier un trajet : le véhicule {vehicule.immatriculation} "
                f"est {vehicule.get_statut_display().lower()} ({vehicule.motif_non_conformite or 'maintenance'})."
            )
        if vehicule and capacite_kg and capacite_kg > vehicule.capacite_kg:
            raise serializers.ValidationError({"capacite_dispo_kg": "La capacité dépasse celle du véhicule."})
        if vehicule and capacite_m3 and capacite_m3 > vehicule.capacite_m3:
            raise serializers.ValidationError({"capacite_dispo_m3": "La capacité dépasse celle du véhicule."})
        return donnees


class TrajetReduitSerializer(serializers.ModelSerializer):
    """Version compacte pour la recherche des PME (module Matching M4)."""

    transporteur_nom = serializers.CharField(source="transporteur.get_full_name", read_only=True)

    class Meta:
        model = Trajet
        fields = [
            "id",
            "transporteur_nom",
            "ville_depart",
            "ville_arrivee",
            "date_depart",
            "capacite_dispo_kg",
            "capacite_dispo_m3",
            "prix_indicatif",
            "statut",
        ]


class EntretienSerializer(serializers.ModelSerializer):
    vehicule_immatriculation = serializers.CharField(source="vehicule.immatriculation", read_only=True)

    class Meta:
        model = Entretien
        fields = [
            "id",
            "vehicule",
            "vehicule_immatriculation",
            "type",
            "date",
            "kilometrage",
            "cout",
            "prochaine_echeance",
        ]
        read_only_fields = ["id"]

    def validate_vehicule(self, vehicule):
        request = self.context.get("request")
        if request and not est_admin(request.user) and vehicule.transporteur_id != request.user.pk:
            raise serializers.ValidationError("Ce véhicule ne vous appartient pas.")
        return vehicule


class FacteurEmissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = FacteurEmission
        fields = ["id", "type_vehicule", "kg_co2_par_km"]


class ImpactSerializer(serializers.Serializer):
    """Réponse de /api/fleet/vehicules/{id}/impact/."""

    nb_trajets = serializers.IntegerField()
    co2_total_kg = serializers.FloatField()
    points_eco = serializers.IntegerField()
