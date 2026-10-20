"""Rôles des utilisateurs. Les mixins d'accès sont dans apps/core/mixins.py."""

from django.db import models


class Role(models.TextChoices):
    PME = "PME", "PME (expéditeur)"
    TRANSPORTEUR = "TRANSPORTEUR", "Transporteur"
    ADMIN = "ADMIN", "Administrateur"


def est_admin(user):
    return user.is_authenticated and (user.is_superuser or getattr(user, "role", None) == Role.ADMIN)
