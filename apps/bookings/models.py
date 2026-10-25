"""M4 — Matching & réservations. Tables : Reservation, HistoriqueStatut, Notification."""

from django.conf import settings
from django.db import models

from apps.core.models import Horodate


class Reservation(Horodate):
    class Statut(models.TextChoices):
        EN_ATTENTE = "EN_ATTENTE", "En attente"
        ACCEPTEE = "ACCEPTEE", "Acceptée"
        REFUSEE = "REFUSEE", "Refusée"
        EN_TRANSIT = "EN_TRANSIT", "En transit"
        LIVREE = "LIVREE", "Livrée"
        ANNULEE = "ANNULEE", "Annulée"

    # Transitions autorisées (diagramme d'états de la présentation)
    TRANSITIONS = {
        Statut.EN_ATTENTE: {Statut.ACCEPTEE, Statut.REFUSEE, Statut.ANNULEE},
        Statut.ACCEPTEE: {Statut.EN_TRANSIT, Statut.ANNULEE},
        Statut.EN_TRANSIT: {Statut.LIVREE},
    }

    expedition = models.ForeignKey("shipments.Expedition", on_delete=models.CASCADE, related_name="reservations")
    trajet = models.ForeignKey("fleet.Trajet", on_delete=models.PROTECT, related_name="reservations")
    statut = models.CharField(max_length=12, choices=Statut.choices, default=Statut.EN_ATTENTE)
    prix_convenu = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    score_matching = models.PositiveSmallIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Réservation #{self.pk}"

    def peut_passer_a(self, nouveau):
        return nouveau in self.TRANSITIONS.get(self.statut, set())

    @property
    def annulable(self):
        return self.peut_passer_a(self.Statut.ANNULEE)


class HistoriqueStatut(models.Model):
    reservation = models.ForeignKey(Reservation, on_delete=models.CASCADE, related_name="historique")
    ancien = models.CharField(max_length=12, choices=Reservation.Statut.choices)
    nouveau = models.CharField(max_length=12, choices=Reservation.Statut.choices)
    par = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    date = models.DateTimeField(auto_now_add=True)
    motif = models.CharField(max_length=255, blank=True)  # ex. annulation pour litige par un administrateur

    class Meta:
        ordering = ["date"]

    def __str__(self):
        return f"{self.ancien} → {self.nouveau}"


class Notification(Horodate):
    destinataire = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    titre = models.CharField(max_length=150)
    message = models.TextField()
    lien = models.CharField(max_length=255, blank=True)
    lu = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]
