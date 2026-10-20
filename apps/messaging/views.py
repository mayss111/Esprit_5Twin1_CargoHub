"""Vues du module Messagerie & support — Membre 1.

Point de départ : une page liste front-office et une page liste back-office.
Ajoutez ici vos vues de création, détail, modification…
"""

from apps.core.views import ListeBackofficeView, ListeFrontView

from .models import Conversation, TicketSupport


class MesConversationsView(ListeFrontView):
    model = Conversation
    roles = []
    titre = "Messagerie"
    sous_titre = "Vos conversations avec les PME et les transporteurs."
    colonnes = [("pk", "N°"), ("reservation", "Réservation"), ("created_at", "Créée le")]

    def get_queryset(self):
        return Conversation.objects.filter(participants=self.request.user)


class BackofficeTicketSupportView(ListeBackofficeView):
    model = TicketSupport
    titre = "Tickets de support"
    colonnes = [
        ("sujet", "Sujet"),
        ("auteur", "Auteur"),
        ("priorite", "Priorité"),
        ("statut", "Statut"),
        ("created_at", "Ouvert le"),
    ]

    def get_queryset(self):
        return TicketSupport.objects.select_related("auteur")
