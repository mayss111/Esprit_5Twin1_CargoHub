"""M1 — Contrats & documents. Tables : Contrat, DocumentTransport."""

from django.db import models

from apps.core.models import Horodate


class Contrat(Horodate):
    reservation = models.OneToOneField("bookings.Reservation", on_delete=models.CASCADE, related_name="contrat")
    fichier = models.FileField(upload_to="contrats/", blank=True)
    signe_par_pme_le = models.DateTimeField(null=True, blank=True)
    signe_par_transporteur_le = models.DateTimeField(null=True, blank=True)

    @property
    def est_signe(self):
        return bool(self.signe_par_pme_le and self.signe_par_transporteur_le)

    def __str__(self):
        return f"Contrat réservation #{self.reservation_id}"


class DocumentTransport(Horodate):
    class Type(models.TextChoices):
        LETTRE_VOITURE = "LETTRE_VOITURE", "Lettre de voiture"
        BON_LIVRAISON = "BON_LIVRAISON", "Bon de livraison"
        AUTRE = "AUTRE", "Autre"

    reservation = models.ForeignKey("bookings.Reservation", on_delete=models.CASCADE, related_name="documents")
    type = models.CharField(max_length=20, choices=Type.choices)
    fichier = models.FileField(upload_to="documents_transport/")

    def __str__(self):
        return f"{self.get_type_display()} #{self.pk}"
