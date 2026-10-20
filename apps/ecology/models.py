"""M3 — Impact écologique. Tables : EmpreinteCarbone, CertificatEco."""

from django.conf import settings
from django.db import models

from apps.core.models import Horodate


class EmpreinteCarbone(Horodate):
    reservation = models.OneToOneField("bookings.Reservation", on_delete=models.CASCADE, related_name="empreinte")
    distance_km = models.FloatField()
    co2_partage_kg = models.FloatField(help_text="CO₂ attribué à l’envoi dans un camion partagé")
    co2_dedie_kg = models.FloatField(help_text="CO₂ si l’envoi avait eu un camion dédié")

    @property
    def co2_economise_kg(self):
        return max(self.co2_dedie_kg - self.co2_partage_kg, 0)


class CertificatEco(Horodate):
    pme = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="certificats_eco")
    periode_debut = models.DateField()
    periode_fin = models.DateField()
    co2_economise_kg = models.FloatField()
    fichier = models.FileField(upload_to="certificats/", blank=True)
