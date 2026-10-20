"""M1 — Comptes & sécurité. Tables : Utilisateur, ProfilPME, ProfilTransporteur."""

from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models

from apps.core.models import Horodate
from apps.core.roles import Role


class UtilisateurManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email, password, **extra):
        if not email:
            raise ValueError("L’email est obligatoire")
        user = self.model(email=self.normalize_email(email), **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra):
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra)

    def create_superuser(self, email, password=None, **extra):
        extra.update(is_staff=True, is_superuser=True, role=Role.ADMIN)
        return self._create_user(email, password, **extra)


class Utilisateur(AbstractUser):
    """Compte unique pour tous : PME, transporteur ou administrateur. Connexion par email."""

    username = None
    email = models.EmailField("email", unique=True)
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.PME)
    telephone = models.CharField(max_length=20, blank=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []
    objects = UtilisateurManager()

    class Meta:
        verbose_name = "utilisateur"

    def __str__(self):
        return self.get_full_name() or self.email


class ProfilPME(Horodate):
    utilisateur = models.OneToOneField(Utilisateur, on_delete=models.CASCADE, related_name="profil_pme")
    raison_sociale = models.CharField(max_length=150)
    matricule_fiscal = models.CharField(max_length=30, blank=True)
    secteur = models.CharField(max_length=100, blank=True)
    adresse = models.CharField(max_length=255, blank=True)
    ville = models.CharField(max_length=80, blank=True)

    class Meta:
        verbose_name = "profil PME"

    def __str__(self):
        return self.raison_sociale


class ProfilTransporteur(Horodate):
    class Statut(models.TextChoices):
        EN_ATTENTE = "EN_ATTENTE", "En attente de validation"
        VALIDE = "VALIDE", "Validé"
        REFUSE = "REFUSE", "Refusé"

    utilisateur = models.OneToOneField(Utilisateur, on_delete=models.CASCADE, related_name="profil_transporteur")
    numero_permis = models.CharField(max_length=30, blank=True)
    permis = models.FileField(upload_to="documents/permis/", blank=True)
    carte_grise = models.FileField(upload_to="documents/cartes_grises/", blank=True)
    statut_validation = models.CharField(max_length=20, choices=Statut.choices, default=Statut.EN_ATTENTE)
    note_moyenne = models.DecimalField(max_digits=3, decimal_places=2, default=0)

    class Meta:
        verbose_name = "profil transporteur"

    def __str__(self):
        return f"Transporteur {self.utilisateur}"
