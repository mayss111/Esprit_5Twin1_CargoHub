"""M2 — Assurance & sinistres. Tables : PoliceAssurance, Sinistre, PieceJustificative."""

from django.db import models

from apps.core.models import Horodate


class PoliceAssurance(Horodate):
    class Statut(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        EXPIREE = "EXPIREE", "Expirée"

    expedition = models.OneToOneField("shipments.Expedition", on_delete=models.CASCADE, related_name="assurance")
    valeur_declaree = models.DecimalField(max_digits=12, decimal_places=2)
    taux = models.DecimalField(max_digits=5, decimal_places=4, default=0.015)
    prime = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    statut = models.CharField(max_length=10, choices=Statut.choices, default=Statut.ACTIVE)

    def __str__(self):
        return f"Police #{self.pk}"


class Sinistre(Horodate):
    class Statut(models.TextChoices):
        DECLARE = "DECLARE", "Déclaré"
        EXPERTISE = "EXPERTISE", "En expertise"
        ACCEPTE = "ACCEPTE", "Accepté"
        REFUSE = "REFUSE", "Refusé"
        REMBOURSE = "REMBOURSE", "Remboursé"

    police = models.ForeignKey(PoliceAssurance, on_delete=models.CASCADE, related_name="sinistres")
    description = models.TextField()
    statut = models.CharField(max_length=10, choices=Statut.choices, default=Statut.DECLARE)
    montant_rembourse = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    def __str__(self):
        return f"Sinistre #{self.pk}"


class PieceJustificative(Horodate):
    sinistre = models.ForeignKey(Sinistre, on_delete=models.CASCADE, related_name="pieces")
    fichier = models.FileField(upload_to="sinistres/")
