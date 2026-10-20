"""M3 — Flotte & trajets. Tables : Vehicule, Trajet, EtapeTrajet."""

from django.conf import settings
from django.db import models

from apps.core.models import Horodate


class Vehicule(Horodate):
    class Type(models.TextChoices):
        CAMIONNETTE = "CAMIONNETTE", "Camionnette"
        CAMION = "CAMION", "Camion"
        SEMI_REMORQUE = "SEMI_REMORQUE", "Semi-remorque"
        FRIGORIFIQUE = "FRIGORIFIQUE", "Frigorifique"

    transporteur = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="vehicules")
    type = models.CharField(max_length=20, choices=Type.choices)
    immatriculation = models.CharField(max_length=20, unique=True)
    capacite_kg = models.PositiveIntegerField()
    capacite_m3 = models.DecimalField(max_digits=6, decimal_places=2)
    conforme = models.BooleanField(default=True)  # mis à False par le module Entretien

    def __str__(self):
        return f"{self.get_type_display()} {self.immatriculation}"


class Trajet(Horodate):
    class Statut(models.TextChoices):
        OUVERT = "OUVERT", "Ouvert aux réservations"
        COMPLET = "COMPLET", "Complet"
        EN_COURS = "EN_COURS", "En cours"
        TERMINE = "TERMINE", "Terminé"
        ANNULE = "ANNULE", "Annulé"

    transporteur = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="trajets")
    vehicule = models.ForeignKey(Vehicule, on_delete=models.PROTECT, related_name="trajets")
    ville_depart = models.CharField(max_length=80)
    ville_arrivee = models.CharField(max_length=80)
    date_depart = models.DateTimeField()
    capacite_dispo_kg = models.DecimalField(max_digits=10, decimal_places=2)
    capacite_dispo_m3 = models.DecimalField(max_digits=8, decimal_places=3)
    prix_indicatif = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    distance_km = models.FloatField(null=True, blank=True)
    recurrent = models.BooleanField(default=False)
    statut = models.CharField(max_length=10, choices=Statut.choices, default=Statut.OUVERT)

    class Meta:
        ordering = ["date_depart"]

    def __str__(self):
        return f"{self.ville_depart} → {self.ville_arrivee} ({self.date_depart:%d/%m})"


class EtapeTrajet(models.Model):
    trajet = models.ForeignKey(Trajet, on_delete=models.CASCADE, related_name="etapes")
    ville = models.CharField(max_length=80)
    ordre = models.PositiveSmallIntegerField()

    class Meta:
        ordering = ["ordre"]
        unique_together = [("trajet", "ordre")]

    def __str__(self):
        return f"{self.ordre}. {self.ville}"
