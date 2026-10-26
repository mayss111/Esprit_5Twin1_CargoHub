"""Serializers du module Flotte — validation serveur, messages en français."""

from django.db.models import Max
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied

from apps.core.roles import est_admin
from apps.maintenance.models import Entretien

from .models import DocumentVehicule, FacteurEmission, Trajet, Vehicule
from .validation import erreur_fichier_vehicule


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
                statut__in=[Trajet.Statut.OUVERT, Trajet.Statut.COMPLET, Trajet.Statut.EN_COURS]
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
    """Même règles que TrajetForm (pages Django). La place libre (capacite_dispo_*) diminue à chaque réservation
    acceptée (module M4) ; on peut envoyer soit la place libre, soit la place proposée (capacite_totale_*)."""

    vehicule_immatriculation = serializers.CharField(source="vehicule.immatriculation", read_only=True)
    etapes = serializers.SlugRelatedField(many=True, read_only=True, slug_field="ville")
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
            "etapes",
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
        read_only_fields = ["id", "statut", "co2_kg", "created_at", "updated_at"]
        extra_kwargs = {"capacite_dispo_kg": {"required": False}, "capacite_dispo_m3": {"required": False}}

    def validate_date_depart(self, valeur):
        if valeur <= timezone.now():
            raise serializers.ValidationError("La date de départ doit être dans le futur.")
        return valeur

    def _capacites(self, donnees, unite):
        """Calcule (place proposée, place libre) pour 'kg' ou 'm3' à partir de ce que le client a envoyé."""
        reserve = getattr(self.instance, f"capacite_reservee_{unite}", 0) if self.instance else 0
        totale, dispo = donnees.get(f"capacite_totale_{unite}"), donnees.get(f"capacite_dispo_{unite}")
        if totale is None and dispo is None:
            if not self.instance:
                raise serializers.ValidationError({f"capacite_dispo_{unite}": "Ce champ est obligatoire."})
            return None
        if totale is None:
            if dispo <= 0:
                raise serializers.ValidationError(
                    {f"capacite_dispo_{unite}": "La capacité disponible doit être supérieure à 0."}
                )
            totale = dispo + reserve
        elif totale <= 0:
            raise serializers.ValidationError(
                {f"capacite_totale_{unite}": "La capacité proposée doit être supérieure à 0."}
            )
        if totale < reserve:
            raise serializers.ValidationError("Impossible de réduire la capacité sous la part déjà réservée.")
        return totale, totale - reserve

    def validate(self, donnees):
        vehicule = donnees.get("vehicule") or (self.instance and self.instance.vehicule)
        request = self.context.get("request")
        if vehicule and request and not est_admin(request.user) and vehicule.transporteur_id != request.user.pk:
            raise PermissionDenied("Ce véhicule ne vous appartient pas.")
        if vehicule and not vehicule.peut_publier_trajet():
            raise serializers.ValidationError(
                f"Impossible de publier un trajet : le véhicule {vehicule.immatriculation} "
                f"est {vehicule.get_statut_display().lower()} ({vehicule.motif_non_conformite or 'maintenance'})."
            )
        depart = donnees.get("ville_depart", getattr(self.instance, "ville_depart", ""))
        arrivee = donnees.get("ville_arrivee", getattr(self.instance, "ville_arrivee", ""))
        if depart and arrivee and depart.strip().casefold() == arrivee.strip().casefold():
            raise serializers.ValidationError(
                {"ville_arrivee": "La ville d'arrivée doit être différente de la ville de départ."}
            )
        for unite, maximum in (("kg", vehicule and vehicule.capacite_kg), ("m3", vehicule and vehicule.capacite_m3)):
            capacites = self._capacites(donnees, unite)
            if capacites is None:
                continue
            totale, dispo = capacites
            if maximum and totale > maximum:
                raise serializers.ValidationError({f"capacite_dispo_{unite}": "La capacité dépasse celle du véhicule."})
            donnees[f"capacite_totale_{unite}"], donnees[f"capacite_dispo_{unite}"] = totale, dispo
        return donnees


class TrajetReduitSerializer(serializers.ModelSerializer):
    """Version compacte pour la recherche des PME."""

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
