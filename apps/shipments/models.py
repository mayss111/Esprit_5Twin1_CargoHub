"""M2 — Expéditions. Tables : Adresse, Expedition, ArticleExpedie."""

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

from apps.core.models import Horodate


class Adresse(models.Model):
    ligne = models.CharField(max_length=255)
    ville = models.CharField(max_length=80)
    code_postal = models.CharField(max_length=10, blank=True)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)

    def __str__(self):
        return f"{self.ligne}, {self.ville}"


class Expedition(Horodate):
    class Statut(models.TextChoices):
        BROUILLON = "BROUILLON", "Brouillon"
        PUBLIEE = "PUBLIEE", "Publiée"
        RESERVEE = "RESERVEE", "Réservée"
        LIVREE = "LIVREE", "Livrée"
        ANNULEE = "ANNULEE", "Annulée"

    pme = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="expeditions")
    adresse_depart = models.ForeignKey(Adresse, on_delete=models.PROTECT, related_name="+")
    adresse_arrivee = models.ForeignKey(Adresse, on_delete=models.PROTECT, related_name="+")
    date_souhaitee = models.DateField()
    description = models.TextField(blank=True)
    statut = models.CharField(max_length=20, choices=Statut.choices, default=Statut.BROUILLON)
    prix_estime = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Expédition #{self.pk} {self.adresse_depart.ville} → {self.adresse_arrivee.ville}"

    @property
    def poids_total_kg(self):
        return sum(a.poids_kg * a.quantite for a in self.articles.all())

    @property
    def volume_total_m3(self):
        return sum(a.volume_m3 * a.quantite for a in self.articles.all())


class ArticleExpedie(models.Model):
    class Type(models.TextChoices):
        GENERAL = "GENERAL", "Marchandise générale"
        ALIMENTAIRE = "ALIMENTAIRE", "Alimentaire"
        TEXTILE = "TEXTILE", "Textile"
        ELECTRONIQUE = "ELECTRONIQUE", "Électronique"
        MATERIAUX = "MATERIAUX", "Matériaux de construction"
        INTERDIT = "INTERDIT", "Interdit au transport"

    expedition = models.ForeignKey(Expedition, on_delete=models.CASCADE, related_name="articles")
    designation = models.CharField(max_length=150)
    type_marchandise = models.CharField(max_length=20, choices=Type.choices, default=Type.GENERAL)
    quantite = models.PositiveIntegerField(default=1)
    poids_kg = models.DecimalField(max_digits=8, decimal_places=2, validators=[MinValueValidator(0)])
    volume_m3 = models.DecimalField(max_digits=8, decimal_places=3, validators=[MinValueValidator(0)])
    fragile = models.BooleanField(default=False)

    def __str__(self):
        return self.designation
