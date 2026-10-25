"""M4 — Appels d'offres & négociation. Tables : AppelOffre, Offre, ContreProposition."""

from django.conf import settings
from django.db import models
from django.utils import timezone

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

    # « Aide au choix » (IA M4) : calculée en arrière-plan par Celery, effacée quand les offres changent.
    class Recommandation(models.TextChoices):
        EN_COURS = "EN_COURS", "Analyse en cours"
        PRETE = "PRETE", "Prête"
        ERREUR = "ERREUR", "Erreur"

    recommandation_ia = models.JSONField(null=True, blank=True)  # {"offre_id", "explication", "methode"}
    recommandation_statut = models.CharField(max_length=10, choices=Recommandation.choices, blank=True)
    recommandation_duree_ms = models.PositiveIntegerField(null=True, blank=True)

    def __str__(self):
        return f"Appel d’offres #{self.pk}"

    def effacer_recommandation(self):
        """Les offres ont changé : l'ancienne recommandation n'est plus valable."""
        AppelOffre.objects.filter(pk=self.pk).update(
            recommandation_ia=None, recommandation_statut="", recommandation_duree_ms=None
        )
        self.recommandation_ia, self.recommandation_statut, self.recommandation_duree_ms = None, "", None

    @property
    def est_ouvert(self):
        """Ouvert ET date limite pas encore passée (la tâche Celery de clôture peut avoir du retard)."""
        return self.statut == self.Statut.OUVERT and self.date_cloture > timezone.now()

    @property
    def modifiable(self):
        """La PME peut modifier ou supprimer son appel tant qu'aucun transporteur n'a répondu."""
        return self.statut == self.Statut.OUVERT and not self.offres.exists()


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
        constraints = [
            models.UniqueConstraint(fields=["appel", "transporteur"], name="une_offre_par_transporteur_et_par_appel")
        ]

    def __str__(self):
        return f"Offre de {self.transporteur} : {self.prix} DT"

    @property
    def modifiable(self):
        return self.statut == self.Statut.PROPOSEE and self.appel.est_ouvert


class ContreProposition(Horodate):
    offre = models.ForeignKey(Offre, on_delete=models.CASCADE, related_name="contre_propositions")
    auteur = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    prix = models.DecimalField(max_digits=10, decimal_places=2)
    message = models.TextField(blank=True)
