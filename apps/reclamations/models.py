import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.models import Horodate


def generer_reference():
    return f"REC-{timezone.now():%Y}-{uuid.uuid4().hex[:8].upper()}"


class Reclamation(Horodate):
    class Type(models.TextChoices):
        RETARD = "RETARD", "Retard de livraison"
        PAIEMENT = "PAIEMENT", "Problème de paiement"
        COMPORTEMENT = "COMPORTEMENT", "Problème de comportement"
        CHARGEMENT = "CHARGEMENT", "Problème de chargement ou de déchargement"
        MANQUANTE = "MANQUANTE", "Marchandise manquante"
        CONDITIONS = "CONDITIONS", "Non-respect des conditions convenues"
        AUTRE = "AUTRE", "Autre"

    class Statut(models.TextChoices):
        EN_ATTENTE = "EN_ATTENTE", "En attente"
        EN_COURS = "EN_COURS", "En cours"
        INFOS = "INFOS", "En attente d'informations"
        RESOLUE = "RESOLUE", "Résolue"
        REJETEE = "REJETEE", "Rejetée"
        ANNULEE = "ANNULEE", "Annulée"

    TRANSITIONS = {
        Statut.EN_ATTENTE: {Statut.EN_COURS, Statut.INFOS, Statut.ANNULEE},
        Statut.EN_COURS: {Statut.INFOS, Statut.RESOLUE, Statut.REJETEE},
        Statut.INFOS: {Statut.EN_COURS, Statut.ANNULEE},
        Statut.RESOLUE: set(),
        Statut.REJETEE: set(),
        Statut.ANNULEE: set(),
    }

    reference = models.CharField(max_length=20, unique=True, default=generer_reference, editable=False)
    auteur = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="reclamations")
    expedition = models.ForeignKey("shipments.Expedition", on_delete=models.PROTECT, related_name="reclamations")
    titre = models.CharField(max_length=150)
    description = models.TextField(max_length=5000)
    type_reclamation = models.CharField(max_length=20, choices=Type.choices)
    statut = models.CharField(max_length=20, choices=Statut.choices, default=Statut.EN_ATTENTE)
    reponse_admin = models.TextField(max_length=3000, blank=True)
    justification_decision = models.TextField(max_length=1500, blank=True)
    assigne_a = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reclamations_assignees",
    )
    resolue_le = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "réclamation"
        verbose_name_plural = "réclamations"

    def __str__(self):
        return f"{self.reference} — {self.titre}"

    @property
    def modifiable_par_auteur(self):
        return self.statut in {self.Statut.EN_ATTENTE, self.Statut.INFOS}

    @property
    def annulable_par_auteur(self):
        return self.modifiable_par_auteur

    def peut_passer_a(self, nouveau_statut):
        return nouveau_statut == self.statut or nouveau_statut in self.TRANSITIONS.get(self.statut, set())

