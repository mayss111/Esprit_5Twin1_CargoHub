"""M2 — Entrepôts & points relais. Tables : Entrepot, CreneauDepot, MouvementColis."""

from django.conf import settings
from django.db import models

from apps.core.models import Horodate


class Entrepot(Horodate):
    nom = models.CharField(max_length=120)
    adresse = models.CharField(max_length=255)
    ville = models.CharField(max_length=80)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    capacite_colis = models.PositiveIntegerField(default=100)
    actif = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.nom} ({self.ville})"


class CreneauDepot(Horodate):
    entrepot = models.ForeignKey(Entrepot, on_delete=models.CASCADE, related_name="creneaux")
    expedition = models.ForeignKey("shipments.Expedition", on_delete=models.CASCADE, related_name="creneaux")
    debut = models.DateTimeField()
    fin = models.DateTimeField()

    class Meta:
        ordering = ["debut"]


class MouvementColis(models.Model):
    class Type(models.TextChoices):
        ENTREE = "ENTREE", "Entrée"
        SORTIE = "SORTIE", "Sortie"

    entrepot = models.ForeignKey(Entrepot, on_delete=models.CASCADE, related_name="mouvements")
    expedition = models.ForeignKey("shipments.Expedition", on_delete=models.CASCADE, related_name="mouvements")
    type = models.CharField(max_length=10, choices=Type.choices)
    scanne_par = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    date = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date"]

    def __str__(self):
        return f"{self.get_type_display()} — {self.expedition}"
