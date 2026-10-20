"""M5 — Fidélité & parrainage. Tables : PointsFidelite, CodePromo, Parrainage."""

from django.conf import settings
from django.db import models

from apps.core.models import Horodate


class PointsFidelite(Horodate):
    utilisateur = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="points")
    solde = models.PositiveIntegerField(default=0)


class CodePromo(Horodate):
    class Type(models.TextChoices):
        POURCENTAGE = "POURCENTAGE", "Pourcentage"
        MONTANT = "MONTANT", "Montant fixe"

    code = models.CharField(max_length=30, unique=True)
    type = models.CharField(max_length=12, choices=Type.choices, default=Type.POURCENTAGE)
    valeur = models.DecimalField(max_digits=8, decimal_places=2)
    montant_minimum = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    date_expiration = models.DateField(null=True, blank=True)
    usage_unique = models.BooleanField(default=False)
    actif = models.BooleanField(default=True)

    def __str__(self):
        return self.code


class Parrainage(Horodate):
    parrain = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="filleuls")
    filleul = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="parrainage")
    recompense_versee = models.BooleanField(default=False)
