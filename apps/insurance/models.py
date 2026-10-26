"""M2 — Assurance & sinistres."""

import uuid

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from apps.core.models import Horodate


def generer_reference_sinistre():
    return f"SIN-{timezone.now():%Y}-{uuid.uuid4().hex[:8].upper()}"


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
    class Type(models.TextChoices):
        DOMMAGE = "DOMMAGE", "Marchandise endommagée"
        PERTE_PARTIELLE = "PERTE_PARTIELLE", "Perte partielle"
        PERTE_TOTALE = "PERTE_TOTALE", "Perte totale"
        ACCIDENT = "ACCIDENT", "Accident"
        VOL = "VOL", "Vol"
        INCENDIE = "INCENDIE", "Incendie"
        AUTRE = "AUTRE", "Autre"

    class Statut(models.TextChoices):
        A_VERIFIER = "A_VERIFIER", "À vérifier"
        EN_COURS = "EN_COURS", "En cours"
        DOCUMENTS = "DOCUMENTS", "En attente de documents"
        ACCEPTE = "ACCEPTE", "Accepté"
        REFUSE = "REFUSE", "Refusé"
        CLOTURE = "CLOTURE", "Clôturé"

    TRANSITIONS = {
        Statut.A_VERIFIER: {Statut.EN_COURS, Statut.DOCUMENTS, Statut.REFUSE},
        Statut.EN_COURS: {Statut.DOCUMENTS, Statut.ACCEPTE, Statut.REFUSE},
        Statut.DOCUMENTS: {Statut.EN_COURS, Statut.REFUSE},
        Statut.ACCEPTE: {Statut.CLOTURE},
        Statut.REFUSE: {Statut.CLOTURE},
        Statut.CLOTURE: set(),
    }

    reference = models.CharField(max_length=20, unique=True, null=True, blank=True, editable=False)
    auteur = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="sinistres"
    )
    expedition = models.ForeignKey(
        "shipments.Expedition", null=True, blank=True, on_delete=models.PROTECT, related_name="sinistres"
    )
    partie_mise_en_cause = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT,
        related_name="sinistres_mis_en_cause",
    )
    police = models.ForeignKey(
        PoliceAssurance, null=True, blank=True, on_delete=models.SET_NULL, related_name="sinistres"
    )
    titre = models.CharField(max_length=150, default="Sinistre")
    description = models.TextField()
    type_sinistre = models.CharField(max_length=20, choices=Type.choices, default=Type.AUTRE)
    date_incident = models.DateField(default=timezone.localdate)
    statut = models.CharField(max_length=20, choices=Statut.choices, default=Statut.A_VERIFIER)
    montant_estime = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(0)]
    )
    montant_rembourse = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    decision_admin = models.TextField(max_length=3000, blank=True)
    justification_decision = models.TextField(max_length=1500, blank=True)
    assigne_a = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="sinistres_assignes"
    )
    resolu_le = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.reference} — {self.titre}"

    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = generer_reference_sinistre()
        super().save(*args, **kwargs)

    @property
    def expedition_effective(self):
        return self.expedition or (self.police.expedition if self.police_id else None)

    @property
    def modifiable_par_auteur(self):
        return self.statut in {self.Statut.A_VERIFIER, self.Statut.DOCUMENTS}

    def peut_passer_a(self, nouveau_statut):
        return nouveau_statut == self.statut or nouveau_statut in self.TRANSITIONS.get(self.statut, set())


class PieceJustificative(Horodate):
    sinistre = models.ForeignKey(Sinistre, on_delete=models.CASCADE, related_name="pieces")
    fichier = models.FileField(upload_to="sinistres/")

    def __str__(self):
        return self.fichier.name.rsplit("/", 1)[-1]

    @property
    def est_image(self):
        return self.fichier.name.lower().endswith((".jpg", ".jpeg", ".png"))

    @property
    def est_pdf(self):
        return self.fichier.name.lower().endswith(".pdf")
