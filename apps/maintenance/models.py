"""M3 — Entretien & conformité. Tables : Entretien, ControleTechnique, DepenseVehicule."""

from django.db import models

from apps.core.models import Horodate


class Entretien(Horodate):
    vehicule = models.ForeignKey("fleet.Vehicule", on_delete=models.CASCADE, related_name="entretiens")
    type = models.CharField(max_length=80)  # vidange, pneus, freins…
    date = models.DateField()
    kilometrage = models.PositiveIntegerField()
    cout = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    prochaine_echeance = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["-date"]


class ControleTechnique(Horodate):
    vehicule = models.ForeignKey("fleet.Vehicule", on_delete=models.CASCADE, related_name="controles")
    date_controle = models.DateField()
    date_expiration = models.DateField()
    favorable = models.BooleanField(default=True)


class DepenseVehicule(Horodate):
    class Categorie(models.TextChoices):
        CARBURANT = "CARBURANT", "Carburant"
        PEAGE = "PEAGE", "Péage"
        REPARATION = "REPARATION", "Réparation"
        AUTRE = "AUTRE", "Autre"

    vehicule = models.ForeignKey("fleet.Vehicule", on_delete=models.CASCADE, related_name="depenses")
    categorie = models.CharField(max_length=12, choices=Categorie.choices)
    montant = models.DecimalField(max_digits=10, decimal_places=2)
    date = models.DateField()
