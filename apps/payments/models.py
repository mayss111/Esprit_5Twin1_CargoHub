"""M5 — Paiement & facturation. Tables : Paiement, Facture, Commission."""

from django.core.exceptions import ValidationError
from django.db import models

from apps.core.models import Horodate


class Paiement(Horodate):
    class Statut(models.TextChoices):
        EN_ATTENTE = "EN_ATTENTE", "En attente"
        PAYE = "PAYE", "Payé"
        ECHOUE = "ECHOUE", "Échoué"
        REMBOURSE = "REMBOURSE", "Remboursé"

    reservation = models.OneToOneField("bookings.Reservation", on_delete=models.PROTECT, related_name="paiement")
    montant = models.DecimalField(max_digits=10, decimal_places=2)
    statut = models.CharField(max_length=12, choices=Statut.choices, default=Statut.EN_ATTENTE)
    code_promo = models.CharField(max_length=30, blank=True)
    stripe_session_id = models.CharField(max_length=255, blank=True)

    def clean(self):
        if self.montant is not None and self.montant <= 0:
            raise ValidationError({"montant": "Le montant doit être supérieur à 0."})

    @property
    def libelle_commission(self):
        try:
            return "Oui" if self.commission.versee else "Non"
        except Commission.DoesNotExist:
            return "—"

    def __str__(self):
        return f"Paiement #{self.pk} — {self.montant} DT"


class Facture(Horodate):
    paiement = models.OneToOneField(Paiement, on_delete=models.PROTECT, related_name="facture")
    numero = models.CharField(max_length=30, unique=True)
    fichier = models.FileField(upload_to="factures/", blank=True)

    def __str__(self):
        return self.numero


class Commission(Horodate):
    paiement = models.OneToOneField(Paiement, on_delete=models.PROTECT, related_name="commission")
    taux = models.DecimalField(max_digits=4, decimal_places=3)
    montant_commission = models.DecimalField(max_digits=10, decimal_places=2)
    montant_transporteur = models.DecimalField(max_digits=10, decimal_places=2)
    versee = models.BooleanField(default=False)
