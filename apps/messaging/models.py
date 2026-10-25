"""M1 — Messagerie & support. Tables : Conversation, Message, TicketSupport."""

from django.conf import settings
from django.db import models

from apps.core.models import Horodate


class Conversation(Horodate):
    participants = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name="conversations")
    bloquee_par = models.ManyToManyField(
        settings.AUTH_USER_MODEL, blank=True, related_name="conversations_bloquees"
    )
    reservation = models.ForeignKey(
        "bookings.Reservation", null=True, blank=True, on_delete=models.SET_NULL, related_name="conversations"
    )

    def __str__(self):
        return f"Conversation #{self.pk}"

    def interlocuteurs(self, user):
        """Les autres participants, vus par `user`."""
        return [p for p in self.participants.all() if p != user]

    def est_bloquee(self):
        return self.bloquee_par.exists()

    def est_bloquee_pour(self, user):
        return self.bloquee_par.filter(pk=user.pk).exists()


class Message(Horodate):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="messages")
    auteur = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    contenu = models.TextField()
    piece_jointe = models.FileField(upload_to="messagerie/", blank=True)
    lu = models.BooleanField(default=False)
    signale = models.BooleanField(default=False)  # rempli par la modération IA
    raison_signalement = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.auteur} : {self.contenu[:40]}"


class TicketSupport(Horodate):
    class Priorite(models.TextChoices):
        BASSE = "BASSE", "Basse"
        NORMALE = "NORMALE", "Normale"
        HAUTE = "HAUTE", "Haute"

    class Statut(models.TextChoices):
        OUVERT = "OUVERT", "Ouvert"
        EN_COURS = "EN_COURS", "En cours"
        RESOLU = "RESOLU", "Résolu"

    auteur = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="tickets")
    sujet = models.CharField(max_length=150)
    description = models.TextField()
    priorite = models.CharField(max_length=10, choices=Priorite.choices, default=Priorite.NORMALE)
    statut = models.CharField(max_length=10, choices=Statut.choices, default=Statut.OUVERT)
    assigne_a = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="tickets_assignes"
    )
    reponse_ia = models.TextField(blank=True)  # première réponse de l'assistant, écrite par une tâche Celery
    reponse_admin = models.TextField(blank=True)

    def __str__(self):
        return self.sujet

    @property
    def modifiable(self):
        """L'auteur peut modifier ou supprimer son ticket tant qu'aucun admin ne l'a pris en charge."""
        return self.statut == self.Statut.OUVERT
