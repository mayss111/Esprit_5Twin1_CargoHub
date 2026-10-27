"""M2 — Expéditions. Tables : Adresse, Expedition, ArticleExpedie.

Les noms de champs déjà lus par les réservations, les entrepôts et l'assurance
sont conservés. Les ajouts préparent la suite sans changer ces modules.
"""

import uuid
from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from apps.core.models import Horodate

# Catégorie refusée à la publication. Une table administrable pourra remplacer
# cette liste plus tard, sans changer le champ type_marchandise.
CATEGORIES_INTERDITES = ("INTERDIT",)

# Une réservation confirmée bloque la modification de l'expédition.
RESERVATIONS_CONFIRMEES = ("ACCEPTEE", "EN_TRANSIT", "LIVREE")


def generer_reference():
    """Référence lisible et unique, par exemple CH-2026-A1B2C3D4."""
    return f"CH-{timezone.now():%Y}-{uuid.uuid4().hex[:8].upper()}"


class Adresse(models.Model):
    """Lieu de départ ou d'arrivée. Réutilisable par plusieurs expéditions."""

    ligne = models.CharField("rue", max_length=255)
    ville = models.CharField(max_length=80)
    gouvernorat = models.CharField(max_length=40, blank=True)
    code_postal = models.CharField(max_length=10, blank=True)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)

    class Meta:
        verbose_name = "adresse"

    def __str__(self):
        if self.gouvernorat:
            return f"{self.ligne}, {self.ville} ({self.gouvernorat})"
        return f"{self.ligne}, {self.ville}"


class Expedition(Horodate):
    """Demande d'envoi d'une PME. created_at et updated_at viennent de Horodate."""

    class Statut(models.TextChoices):
        BROUILLON = "BROUILLON", "Brouillon"
        PUBLIEE = "PUBLIEE", "Publiée"
        A_VERIFIER = "A_VERIFIER", "À vérifier"
        REFUSEE = "REFUSEE", "Refusée"
        RESERVEE = "RESERVEE", "Réservée"
        LIVREE = "LIVREE", "Livrée"
        ANNULEE = "ANNULEE", "Annulée"

    reference = models.CharField(max_length=20, unique=True, default=generer_reference, editable=False)
    pme = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="expeditions",
        verbose_name="PME",
    )
    # PROTECT : une adresse encore citée par une expédition ne peut pas disparaître.
    # related_name="+" : deux liens vers Adresse, sans nom inverse en double.
    adresse_depart = models.ForeignKey(Adresse, on_delete=models.PROTECT, related_name="+")
    adresse_arrivee = models.ForeignKey(Adresse, on_delete=models.PROTECT, related_name="+")
    date_souhaitee = models.DateField("date de départ")
    date_arrivee = models.DateField("date d'arrivée")
    description = models.TextField(blank=True)
    statut = models.CharField(max_length=20, choices=Statut.choices, default=Statut.BROUILLON)
    # Réservé à une estimation future. Cette version ne calcule pas de prix.
    prix_estime = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    motif_decision = models.TextField("motif de la décision", blank=True)
    empreinte_verification = models.CharField(max_length=64, blank=True)
    verifie_le = models.DateTimeField(null=True, blank=True)
    duree_verification_ms = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "expédition"

    def __str__(self):
        return f"{self.reference} {self.adresse_depart.ville} → {self.adresse_arrivee.ville}"

    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = generer_reference()
        super().save(*args, **kwargs)

    @property
    def poids_total_kg(self):
        return sum((a.poids_kg * a.quantite for a in self.articles.all()), Decimal("0"))

    @property
    def volume_total_m3(self):
        return sum((a.volume_m3 * a.quantite for a in self.articles.all()), Decimal("0"))

    def a_une_reservation_confirmee(self):
        return self.reservations.filter(statut__in=RESERVATIONS_CONFIRMEES).exists()

    def peut_etre_modifiee(self):
        modifiables = {
            self.Statut.BROUILLON,
            self.Statut.PUBLIEE,
            self.Statut.REFUSEE,
            self.Statut.A_VERIFIER,
        }
        return self.statut in modifiables and not self.a_une_reservation_confirmee()

    def peut_etre_annulee(self):
        return self.peut_etre_modifiee()

    @property
    def controles_recents(self):
        if self.verifie_le is None:
            return self.controles.none()
        return self.controles.filter(verifie_le=self.verifie_le)

    def bon_disponible(self):
        """Bon de transport utilisable : l'expédition a déjà été autorisée."""
        return self.statut in {self.Statut.PUBLIEE, self.Statut.RESERVEE, self.Statut.LIVREE}

    def peut_etre_supprimee(self):
        return False


class ArticleExpedie(models.Model):
    """Ligne de marchandise. Une expédition en contient plusieurs."""

    class Type(models.TextChoices):
        GENERAL = "GENERAL", "Marchandise générale"
        ALIMENTAIRE = "ALIMENTAIRE", "Alimentaire"
        TEXTILE = "TEXTILE", "Textile"
        ELECTRONIQUE = "ELECTRONIQUE", "Électronique"
        MATERIAUX = "MATERIAUX", "Matériaux de construction"
        INTERDIT = "INTERDIT", "Interdit au transport"

    # CASCADE : les articles n'existent pas sans leur expédition.
    expedition = models.ForeignKey(Expedition, on_delete=models.CASCADE, related_name="articles")
    designation = models.CharField("nom de l'article", max_length=150)
    description = models.TextField(blank=True)
    type_marchandise = models.CharField(
        "catégorie",
        max_length=20,
        choices=Type.choices,
        default=Type.GENERAL,
    )
    quantite = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])
    poids_kg = models.DecimalField(
        "poids (kg)",
        max_digits=8,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    volume_m3 = models.DecimalField(
        "volume (m³)",
        max_digits=8,
        decimal_places=3,
        validators=[MinValueValidator(Decimal("0.001"))],
    )
    fragile = models.BooleanField(default=False)
    valeur_declaree = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
    )

    class Meta:
        verbose_name = "article expédié"
        verbose_name_plural = "articles expédiés"

    def __str__(self):
        return self.designation

    @property
    def est_interdit(self):
        return self.type_marchandise in CATEGORIES_INTERDITES


class RegleInterdite(Horodate):
    """Règle CargoHub. Gemini ne décide pas seul : seule une règle active confirme un refus."""

    nom = models.CharField(max_length=80, unique=True)
    description = models.TextField()
    motif = models.TextField("motif d'interdiction")
    mots_cles = models.CharField(
        max_length=255,
        help_text="Mots séparés par des virgules, cherchés dans le nom et la description.",
    )
    actif = models.BooleanField(default=True)

    class Meta:
        ordering = ["nom"]
        verbose_name = "règle d'interdiction"
        verbose_name_plural = "règles d'interdiction"

    def __str__(self):
        return self.nom

    def mots(self):
        return [mot.casefold() for mot in self.mots_lisibles()]

    def mots_lisibles(self):
        return [mot.strip() for mot in self.mots_cles.split(",") if mot.strip()]


class ControleArticle(models.Model):
    """Résultat d'une vérification pour un article. Les lots précédents sont conservés."""

    class Risque(models.TextChoices):
        FAIBLE = "FAIBLE", "Faible"
        MOYEN = "MOYEN", "Moyen"
        ELEVE = "ELEVE", "Élevé"
        INCONNU = "INCONNU", "Inconnu"

    class Decision(models.TextChoices):
        AUTORISE = "AUTORISE", "Autorisé"
        A_VERIFIER = "A_VERIFIER", "À vérifier"
        REFUSE = "REFUSE", "Refusé"

    expedition = models.ForeignKey(Expedition, on_delete=models.CASCADE, related_name="controles")
    article = models.ForeignKey(ArticleExpedie, null=True, blank=True, on_delete=models.SET_NULL)
    identifiant_article = models.PositiveIntegerField()
    nom = models.CharField(max_length=150)
    categorie_declaree = models.CharField(max_length=20)
    categorie_proposee = models.CharField(max_length=80, blank=True)
    risque = models.CharField(max_length=10, choices=Risque.choices, default=Risque.INCONNU)
    suspicion = models.BooleanField(default=False)
    verification_manuelle = models.BooleanField(default=False)
    motif = models.TextField(blank=True)
    informations = models.TextField(blank=True)
    decision = models.CharField(max_length=12, choices=Decision.choices)
    regle = models.ForeignKey(RegleInterdite, null=True, blank=True, on_delete=models.SET_NULL)
    verifie_le = models.DateTimeField()

    class Meta:
        ordering = ["identifiant_article"]
        verbose_name = "contrôle d'article"

    def __str__(self):
        return f"{self.nom} ({self.get_decision_display()})"
