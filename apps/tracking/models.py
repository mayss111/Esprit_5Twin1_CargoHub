"""M5 — Suivi & livraison. Tables : SuiviPosition, PreuveLivraison, Incident, Avis."""

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.core.models import Horodate


class SuiviPosition(models.Model):
    reservation = models.ForeignKey("bookings.Reservation", on_delete=models.CASCADE, related_name="positions")
    latitude = models.FloatField()
    longitude = models.FloatField()
    date = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date"]

    def __str__(self):
        return f"{self.latitude}, {self.longitude}"


class PreuveLivraison(Horodate):
    reservation = models.OneToOneField("bookings.Reservation", on_delete=models.CASCADE, related_name="preuve")
    code_otp = models.CharField(max_length=6)
    photo = models.ImageField(upload_to="preuves/", blank=True)
    confirmee_le = models.DateTimeField(null=True, blank=True)


class Incident(Horodate):
    class Type(models.TextChoices):
        RETARD = "RETARD", "Retard"
        DOMMAGE = "DOMMAGE", "Marchandise abîmée"
        MANQUANT = "MANQUANT", "Colis manquant"
        AUTRE = "AUTRE", "Autre"

    class Statut(models.TextChoices):
        OUVERT = "OUVERT", "Ouvert"
        RESOLU = "RESOLU", "Résolu"

    reservation = models.ForeignKey("bookings.Reservation", on_delete=models.CASCADE, related_name="incidents")
    declare_par = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    type = models.CharField(max_length=10, choices=Type.choices)
    description = models.TextField()
    statut = models.CharField(max_length=10, choices=Statut.choices, default=Statut.OUVERT)


class Avis(Horodate):
    class Sentiment(models.TextChoices):
        POSITIF = "POSITIF", "Positif"
        NEUTRE = "NEUTRE", "Neutre"
        NEGATIF = "NEGATIF", "Négatif"

    reservation = models.ForeignKey("bookings.Reservation", on_delete=models.CASCADE, related_name="avis")
    auteur = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="avis_donnes")
    cible = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="avis_recus")
    note = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    commentaire = models.TextField(blank=True)
    sentiment = models.CharField(max_length=10, choices=Sentiment.choices, blank=True)  # rempli par l'IA

    class Meta:
        verbose_name_plural = "avis"
        unique_together = [("reservation", "auteur")]
