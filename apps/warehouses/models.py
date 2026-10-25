"""M2 — Entrepôts & points relais. Tables : Entrepot, CreneauDepot, MouvementColis."""

import uuid
from datetime import time, timedelta
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import DecimalField, ExpressionWrapper, F, Q, Sum
from django.utils import timezone

from apps.core.models import Horodate


def generer_reference_depot():
    """Référence lisible, par exemple DP-2026-A1B2C3D4."""
    return f"DP-{timezone.now():%Y}-{uuid.uuid4().hex[:8].upper()}"


class Entrepot(Horodate):
    """Point relais. created_at et updated_at viennent de Horodate.

    capacite_colis reste le compteur historique. La capacité utilisée pour
    le stockage est capacite_max_m3.
    """

    nom = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    adresse = models.CharField("adresse", max_length=255)
    ville = models.CharField(max_length=80)
    gouvernorat = models.CharField(max_length=40, blank=True)
    code_postal = models.CharField(max_length=10, blank=True)
    latitude = models.FloatField(
        null=True,
        blank=True,
        validators=[MinValueValidator(-90), MaxValueValidator(90)],
    )
    longitude = models.FloatField(
        null=True,
        blank=True,
        validators=[MinValueValidator(-180), MaxValueValidator(180)],
    )
    capacite_colis = models.PositiveIntegerField(default=100)
    capacite_max_m3 = models.DecimalField(
        "capacité maximale (m³)",
        max_digits=8,
        decimal_places=3,
        default=Decimal("10"),
        validators=[MinValueValidator(Decimal("0.001"), "La capacité doit être strictement positive.")],
    )
    horaire_ouverture = models.TimeField("ouverture", default=time(8, 0))
    horaire_fermeture = models.TimeField("fermeture", default=time(18, 0))
    duree_stockage_max_heures = models.PositiveIntegerField(
        "durée maximale de stockage (heures)",
        default=48,
        validators=[MinValueValidator(1)],
        help_text="Durée prévue après le début du dépôt. 48 heures par défaut.",
    )
    delai_grace_minutes = models.PositiveIntegerField(
        "délai de grâce (minutes)",
        default=30,
        validators=[MinValueValidator(0)],
        help_text="Délai après la fin du créneau avant de classer une réservation non déclarée comme absente.",
    )
    actif = models.BooleanField(
        default=True,
        help_text="Un entrepôt inactif reste dans l'historique mais n'accepte plus de dépôt.",
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "entrepôt"
        constraints = [
            models.UniqueConstraint(
                fields=["nom", "ville"],
                name="entrepot_nom_ville_unique",
                violation_error_message="Un entrepôt porte déjà ce nom dans cette ville.",
            )
        ]

    def __str__(self):
        return f"{self.nom} ({self.ville})"

    def clean(self):
        super().clean()
        erreurs = {}
        if (self.latitude is None) != (self.longitude is None):
            erreurs["latitude"] = "Indiquez la latitude et la longitude ensemble."
        if self.horaire_ouverture and self.horaire_fermeture and self.horaire_fermeture <= self.horaire_ouverture:
            erreurs["horaire_fermeture"] = "L'heure de fermeture doit être après l'heure d'ouverture."
        if erreurs:
            raise ValidationError(erreurs)

    def volume_present_m3(self):
        """Volume des expéditions dont le dernier mouvement ici est une entrée."""
        from apps.shipments.models import ArticleExpedie

        vus = set()
        presents = []
        for mouvement in self.mouvements.order_by("expedition_id", "-date", "-pk"):
            if mouvement.expedition_id in vus:
                continue
            vus.add(mouvement.expedition_id)
            if mouvement.type == MouvementColis.Type.ENTREE:
                presents.append(mouvement.expedition_id)
        if not presents:
            return Decimal("0")
        total = ArticleExpedie.objects.filter(expedition_id__in=presents).aggregate(
            total=Sum(
                ExpressionWrapper(
                    F("volume_m3") * F("quantite"),
                    output_field=DecimalField(max_digits=14, decimal_places=3),
                )
            )
        )["total"]
        return total or Decimal("0")


class CreneauDepot(Horodate):
    """Réservation d'un créneau de dépôt.

    debut et fin sont le créneau de dépôt de 2 heures.
    fin_stockage_prevue est la fin de réservation choisie par la PME.
    Le volume compte dès la confirmation et jusqu'à cette fin, puis le statut
    passe à Terminé. L'historique des statuts annulés et terminés est conservé.
    """

    class Statut(models.TextChoices):
        RESERVE = "RESERVE", "Réservé"
        DEPOT_DECLARE = "DEPOT_DECLARE", "Dépôt déclaré"
        EFFECTUE = "EFFECTUE", "Déposé confirmé"
        TERMINE = "TERMINE", "Terminé"
        ANNULE = "ANNULE", "Annulé"
        NO_SHOW = "NO_SHOW", "Absent"

    reference = models.CharField(max_length=20, unique=True, editable=False)
    entrepot = models.ForeignKey(Entrepot, on_delete=models.CASCADE, related_name="creneaux")
    expedition = models.ForeignKey("shipments.Expedition", on_delete=models.CASCADE, related_name="creneaux")
    debut = models.DateTimeField("début du créneau")
    fin = models.DateTimeField("fin du créneau")
    volume_reserve = models.DecimalField(
        "volume réservé (m³)",
        max_digits=12,
        decimal_places=3,
        null=True,
        blank=True,
    )
    fin_stockage_prevue = models.DateTimeField(
        "fin de réservation",
        null=True,
        blank=True,
        help_text="Choisie par la PME. Le volume réservé est libéré à cet instant.",
    )
    declare_le = models.DateTimeField("dépôt déclaré le", null=True, blank=True)
    statut = models.CharField(max_length=20, choices=Statut.choices, default=Statut.RESERVE)
    motif_annulation = models.TextField(blank=True)

    class Meta:
        ordering = ["debut"]
        verbose_name = "créneau de dépôt"
        constraints = [
            models.UniqueConstraint(
                fields=["expedition"],
                condition=Q(statut__in=["RESERVE", "DEPOT_DECLARE", "EFFECTUE"]),
                name="un_depot_actif_par_expedition",
                violation_error_message="Cette expédition a déjà un dépôt réservé.",
            ),
            models.CheckConstraint(
                condition=Q(fin__gt=F("debut")),
                name="creneau_fin_apres_debut",
                violation_error_message="L'heure de fin doit être après l'heure de début.",
            ),
        ]
        indexes = [
            models.Index(fields=["entrepot", "statut", "debut"], name="creneau_entrepot_statut_debut"),
        ]

    def __str__(self):
        return f"{self.reference} — {self.entrepot}"

    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = generer_reference_depot()
        super().save(*args, **kwargs)

    def clean(self):
        super().clean()
        if self.debut and self.fin and self.fin <= self.debut:
            raise ValidationError({"fin": "L'heure de fin doit être après l'heure de début."})

    @property
    def date_depot(self):
        return timezone.localtime(self.debut).date()

    @property
    def heure_debut(self):
        return timezone.localtime(self.debut).time().replace(microsecond=0)

    @property
    def heure_fin(self):
        return timezone.localtime(self.fin).time().replace(microsecond=0)

    def annulable_par_pme(self):
        return self.statut == self.Statut.RESERVE

    def peut_declarer(self, maintenant=None):
        """La PME peut signaler son arrivée pendant le créneau et le délai de grâce.

        Cette déclaration n'est pas une preuve de dépôt physique.
        """
        maintenant = maintenant or timezone.now()
        if self.statut != self.Statut.RESERVE:
            return False
        grace = timedelta(minutes=self.entrepot.delai_grace_minutes)
        return self.debut <= maintenant <= self.fin + grace

    def nom_pme(self):
        profil = getattr(self.expedition.pme, "profil_pme", None)
        if profil and profil.raison_sociale:
            return profil.raison_sociale
        return self.expedition.pme.get_full_name() or self.expedition.pme.email


class MouvementColis(models.Model):
    """Entrée ou sortie physique. Créé plus tard par le scan, jamais par la réservation."""

    class Type(models.TextChoices):
        ENTREE = "ENTREE", "Entrée"
        SORTIE = "SORTIE", "Sortie"

    entrepot = models.ForeignKey(Entrepot, on_delete=models.CASCADE, related_name="mouvements")
    expedition = models.ForeignKey("shipments.Expedition", on_delete=models.CASCADE, related_name="mouvements")
    creneau = models.ForeignKey(
        CreneauDepot,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="mouvements",
        help_text="Lien prévu pour le scan d'entrée. Reste vide tant que le colis n'est pas passé.",
    )
    type = models.CharField("type de mouvement", max_length=10, choices=Type.choices)
    scanne_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name="mouvements_colis",
        verbose_name="effectué par",
    )
    date = models.DateTimeField("date et heure", default=timezone.now)
    commentaire = models.TextField(blank=True)
    exceptionnel = models.BooleanField(
        default=False,
        help_text="Entrée acceptée par un administrateur en dehors du créneau de 2 heures.",
    )
    ouvert = models.BooleanField(default=False)
    prolongation_heures = models.PositiveIntegerField(default=0)
    motif_prolongation = models.TextField(blank=True)

    class Meta:
        ordering = ["-date"]
        constraints = [
            models.UniqueConstraint(
                fields=["expedition"],
                condition=Q(ouvert=True),
                name="une_entree_ouverte_par_expedition",
                violation_error_message="Une entrée est déjà enregistrée pour cette expédition.",
            )
        ]

    def __str__(self):
        return f"{self.get_type_display()} — {self.expedition}"
