"""M3 — Flotte & trajets. Tables : Vehicule, Trajet, EtapeTrajet, DocumentVehicule, FacteurEmission."""

from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from apps.core.models import Horodate

# Délai avant lequel on rappelle qu'un document arrive à expiration (Celery).
JOURS_ALERTE_EXPIRATION = 30


class Vehicule(Horodate):
    class Type(models.TextChoices):
        CAMIONNETTE = "CAMIONNETTE", "Camionnette"
        CAMION = "CAMION", "Camion"
        SEMI_REMORQUE = "SEMI_REMORQUE", "Semi-remorque"
        FRIGORIFIQUE = "FRIGORIFIQUE", "Frigorifique"

    class Statut(models.TextChoices):
        ACTIF = "ACTIF", "Actif"
        EN_MAINTENANCE = "EN_MAINTENANCE", "En maintenance"
        NON_CONFORME = "NON_CONFORME", "Non conforme"

    transporteur = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="vehicules")
    type = models.CharField(max_length=20, choices=Type.choices)
    immatriculation = models.CharField(max_length=20, unique=True)
    capacite_kg = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    capacite_m3 = models.DecimalField(max_digits=6, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    conforme = models.BooleanField(default=True)  # mis à False par le module Entretien
    statut = models.CharField(max_length=15, choices=Statut.choices, default=Statut.ACTIF)
    motif_non_conformite = models.CharField(max_length=255, blank=True)

    class Meta:
        verbose_name = "véhicule"

    def __str__(self):
        return f"{self.get_type_display()} {self.immatriculation}"

    # ------------------------------------------------------------- conformité
    @property
    def documents_expirent_bientot(self):
        """Documents (carte grise, assurance) qui expirent dans moins de 30 jours ou déjà expirés."""
        limite = timezone.localdate() + timedelta(days=JOURS_ALERTE_EXPIRATION)
        return self.documents.filter(date_expiration__lte=limite)

    def raisons_non_conformite(self):
        """Liste des raisons qui rendent le véhicule inapte au transport."""
        raisons = []
        aujourd_hui = timezone.localdate()
        for doc in self.documents.filter(date_expiration__lt=aujourd_hui):
            raisons.append(f"{doc.get_type_display()} expiré le {doc.date_expiration:%d/%m/%Y}")
        dernier_ct = self.controles.order_by("-date_controle").first()
        if dernier_ct and (dernier_ct.date_expiration < aujourd_hui or not dernier_ct.favorable):
            raisons.append("Contrôle technique expiré ou défavorable")
        return raisons

    def est_non_conforme(self):
        """True si un document est expiré ou si le contrôle technique est expiré/défavorable."""
        return bool(self.raisons_non_conformite())

    def recalculer_conformite(self, sauvegarder=True):
        """Met conforme et statut à jour. Retourne le statut effectif."""
        if self.est_non_conforme():
            self.conforme = False
            self.statut = self.Statut.NON_CONFORME
            self.motif_non_conformite = " ; ".join(self.raisons_non_conformite())
        elif self.statut == self.Statut.NON_CONFORME:
            self.conforme = True
            self.statut = self.Statut.ACTIF
            self.motif_non_conformite = ""
        if sauvegarder:
            self.save(update_fields=["conforme", "statut", "motif_non_conformite"])
        return self.statut

    def peut_publier_trajet(self):
        """Un véhicule non conforme ou en maintenance ne peut pas publier de trajet."""
        return self.statut == self.Statut.ACTIF and self.conforme

    def clean(self):
        if self.capacite_kg < 1:
            raise ValidationError({"capacite_kg": "La capacité doit être d'au moins 1 kg."})
        if self.capacite_m3 <= 0:
            raise ValidationError({"capacite_m3": "La capacité doit être supérieure à 0 m³."})


class DocumentVehicule(Horodate):
    """Carte grise ou assurance d'un véhicule, avec date d'expiration."""

    class Type(models.TextChoices):
        CARTE_GRISE = "CARTE_GRISE", "Carte grise"
        ASSURANCE = "ASSURANCE", "Assurance"

    vehicule = models.ForeignKey(Vehicule, on_delete=models.CASCADE, related_name="documents")
    type = models.CharField(max_length=20, choices=Type.choices)
    fichier = models.FileField(upload_to="vehicules/documents/")
    date_expiration = models.DateField()

    class Meta:
        verbose_name = "document véhicule"
        unique_together = [("vehicule", "type")]

    def __str__(self):
        return f"{self.get_type_display()} — {self.vehicule.immatriculation}"


class Trajet(Horodate):
    class Statut(models.TextChoices):
        PUBLIE = "PUBLIE", "Publié"
        COMPLET = "COMPLET", "Complet"
        EN_COURS = "EN_COURS", "En cours"
        TERMINE = "TERMINE", "Terminé"
        ANNULE = "ANNULE", "Annulé"

    transporteur = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="trajets")
    vehicule = models.ForeignKey(Vehicule, on_delete=models.PROTECT, related_name="trajets")
    ville_depart = models.CharField(max_length=80)
    ville_arrivee = models.CharField(max_length=80)
    date_depart = models.DateTimeField()
    capacite_dispo_kg = models.DecimalField(
        max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))]
    )
    capacite_dispo_m3 = models.DecimalField(
        max_digits=8, decimal_places=3, validators=[MinValueValidator(Decimal("0.001"))]
    )
    capacite_totale_kg = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True, help_text="Figée à la publication"
    )
    capacite_totale_m3 = models.DecimalField(max_digits=8, decimal_places=3, null=True, blank=True)
    prix_indicatif = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    distance_km = models.FloatField(null=True, blank=True)
    recurrent = models.BooleanField(default=False)
    statut = models.CharField(max_length=10, choices=Statut.choices, default=Statut.PUBLIE)
    co2_kg = models.FloatField(null=True, blank=True, help_text="CO₂ émis pour ce trajet (kg)")

    class Meta:
        ordering = ["date_depart"]

    def __str__(self):
        return f"{self.ville_depart} → {self.ville_arrivee} ({self.date_depart:%d/%m})"

    def clean(self):
        if self.date_depart and self.date_depart <= timezone.now():
            raise ValidationError({"date_depart": "La date de départ doit être dans le futur."})
        if self.capacite_dispo_kg is not None and self.capacite_dispo_kg <= 0:
            raise ValidationError({"capacite_dispo_kg": "La capacité disponible doit être supérieure à 0."})
        if self.capacite_dispo_m3 is not None and self.capacite_dispo_m3 <= 0:
            raise ValidationError({"capacite_dispo_m3": "La capacité disponible doit être supérieure à 0."})
        if self.vehicule_id:
            if self.capacite_dispo_kg and self.capacite_dispo_kg > self.vehicule.capacite_kg:
                raise ValidationError({"capacite_dispo_kg": "La capacité dépasse celle du véhicule."})
            if self.capacite_dispo_m3 and self.capacite_dispo_m3 > self.vehicule.capacite_m3:
                raise ValidationError({"capacite_dispo_m3": "La capacité dépasse celle du véhicule."})

    # ------------------------------------------------------------- réservations
    @property
    def capacite_reservee_kg(self):
        """Somme des expéditions acceptées (ou en transit / livrées) sur ce trajet."""

        stats = ("ACCEPTEE", "EN_TRANSIT", "LIVREE")
        total = Decimal("0")
        for res in self.reservations.filter(statut__in=stats).select_related("expedition"):
            total += res.expedition.poids_total_kg
        return total

    @property
    def capacite_reservee_m3(self):

        stats = ("ACCEPTEE", "EN_TRANSIT", "LIVREE")
        total = Decimal("0")
        for res in self.reservations.filter(statut__in=stats).select_related("expedition"):
            total += res.expedition.volume_total_m3
        return total

    @property
    def taux_remplissage(self):
        """Taux de remplissage (0–1) basé sur le poids."""
        if not self.capacite_totale_kg:
            return 0
        return min(float(self.capacite_reservee_kg / self.capacite_totale_kg), 1.0)

    def peut_accepter(self, poids_kg, volume_m3):
        """True si une expédition de ce poids/volume tient encore dans le trajet."""
        return self.capacite_dispo_kg >= Decimal(str(poids_kg)) and self.capacite_dispo_m3 >= Decimal(str(volume_m3))

    def reserver_capacite(self, poids_kg, volume_m3):
        """Déduit la capacité d'une réservation acceptée, atomiquement.

        Lève ValueError si la capacité restante est insuffisante (anti-surbooking).
        """
        poids, volume = Decimal(str(poids_kg)), Decimal(str(volume_m3))
        if poids > self.capacite_dispo_kg or volume > self.capacite_dispo_m3:
            raise ValueError("Capacité insuffisante sur ce trajet.")
        self.capacite_dispo_kg -= poids
        self.capacite_dispo_m3 -= volume
        if self.capacite_dispo_kg <= 0 or self.capacite_dispo_m3 <= 0:
            self.statut = self.Statut.COMPLET
        self.save(update_fields=["capacite_dispo_kg", "capacite_dispo_m3", "statut"])

    def liberer_capacite(self, poids_kg, volume_m3):
        """Rend la capacité d'une réservation annulée/refusée."""
        self.capacite_dispo_kg += Decimal(str(poids_kg))
        self.capacite_dispo_m3 += Decimal(str(volume_m3))
        if self.statut == self.Statut.COMPLET:
            self.statut = self.Statut.PUBLIE
        self.save(update_fields=["capacite_dispo_kg", "capacite_dispo_m3", "statut"])

    # ------------------------------------------------------------- matching (M4)
    def est_compatible(self, expedition):
        """Service appelé par le module Matching : ce trajet convient-il à l'expédition ?"""
        if self.statut != self.Statut.PUBLIE:
            return False
        if self.date_depart <= timezone.now():
            return False
        if not self.vehicule.peut_publier_trajet():
            return False
        if self.ville_depart.lower() != expedition.adresse_depart.ville.strip().lower():
            return False
        if self.ville_arrivee.lower() != expedition.adresse_arrivee.ville.strip().lower():
            return False
        if expedition.date_souhaitee and self.date_depart.date() != expedition.date_souhaitee:
            return False
        return self.peut_accepter(expedition.poids_total_kg, expedition.volume_total_m3)


class EtapeTrajet(models.Model):
    trajet = models.ForeignKey(Trajet, on_delete=models.CASCADE, related_name="etapes")
    ville = models.CharField(max_length=80)
    ordre = models.PositiveSmallIntegerField()

    class Meta:
        ordering = ["ordre"]
        unique_together = [("trajet", "ordre")]

    def __str__(self):
        return f"{self.ordre}. {self.ville}"


class FacteurEmission(models.Model):
    """Facteur CO₂ par type de véhicule, administrable par l'admin (back-office)."""

    type_vehicule = models.CharField(max_length=20, choices=Vehicule.Type.choices, unique=True)
    kg_co2_par_km = models.DecimalField(
        max_digits=6, decimal_places=4, validators=[MinValueValidator(Decimal("0.0001"))]
    )

    class Meta:
        verbose_name = "facteur d'émission"

    def __str__(self):
        return f"{self.get_type_vehicule_display()} : {self.kg_co2_par_km} kg CO₂/km"

    @classmethod
    def pour(cls, type_vehicule):
        """Facteur par défaut si l'admin n'a rien défini."""
        return cls.objects.get_or_create(type_vehicule=type_vehicule, defaults={"kg_co2_par_km": Decimal("0.2500")})[
            0
        ].kg_co2_par_km
