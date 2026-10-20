from django.db import models


class Horodate(models.Model):
    """Ajoute created_at / updated_at à un modèle. À hériter dans toutes les apps."""

    created_at = models.DateTimeField("créé le", auto_now_add=True)
    updated_at = models.DateTimeField("modifié le", auto_now=True)

    class Meta:
        abstract = True
        ordering = ["-created_at"]
