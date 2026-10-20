"""M4 — Appels d'offres & négociation. Tables : AppelOffre, Offre, ContreProposition."""

from django.conf import settings
from django.db import models

from apps.core.models import Horodate


class AppelOffre(Horodate):
    class Statut(models.TextChoices):
        OUVERT = "OUVERT", "Ouvert"
        CLOTURE = "CLOTURE", "Clôturé"
        ATTRIBUE = "ATTRIBUE", "Attribué"
        ANNULE = "ANNULE", "Annulé"

    expedition = models.OneToOneField("shipments.Expedition", on_delete=models.CASCADE, related_name="appel_offre")
    date_cloture = models.DateTimeField()
    prix_max = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    statut = models.CharField(max_length=10, choices=Statut.choices, default=Statut.OUVERT)

    def __str__(self):
        return f"Appel d’offres #{self.pk}"


class Offre(Horodate):
    class Statut(models.TextChoices):
        PROPOSEE = "PROPOSEE", "Proposée"
        RETENUE = "RETENUE", "Retenue"
        REJETEE = "REJETEE", "Rejetée"

    appel = models.ForeignKey(AppelOffre, on_delete=models.CASCADE, related_name="offres")
    transporteur = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="offres")
    trajet = models.ForeignKey("fleet.Trajet", null=True, blank=True, on_delete=models.SET_NULL)
    prix = models.DecimalField(max_digits=10, decimal_places=2)
    message = models.TextField(blank=True)
    statut = models.CharField(max_length=10, choices=Statut.choices, default=Statut.PROPOSEE)

    class Meta:
        ordering = ["prix"]


class ContreProposition(Horodate):
    offre = models.ForeignKey(Offre, on_delete=models.CASCADE, related_name="contre_propositions")
    auteur = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    prix = models.DecimalField(max_digits=10, decimal_places=2)
    message = models.TextField(blank=True)
