from django.urls import path

from . import views

# Front-office (PME et transporteurs)
urlpatterns = [
    path("", views.MesConversationsView.as_view(), name="liste"),
    path("nouvelle/", views.NouvelleConversationView.as_view(), name="nouvelle"),
    path("<int:pk>/", views.ConversationDetailView.as_view(), name="conversation"),
    path("<int:pk>/bloquer/", views.ConversationBloquerView.as_view(), name="conversation_bloquer"),
    path("<int:pk>/debloquer/", views.ConversationDebloquerView.as_view(), name="conversation_debloquer"),
    path("message/<int:pk>/supprimer/", views.MessageSupprimerView.as_view(), name="message_supprimer"),
    path("assistant/", views.AssistantSupportView.as_view(), name="assistant"),
    path("tickets/", views.MesTicketsView.as_view(), name="tickets"),
    path("tickets/nouveau/", views.TicketCreerView.as_view(), name="ticket_creer"),
    path("tickets/<int:pk>/", views.TicketDetailView.as_view(), name="ticket"),
    path("tickets/<int:pk>/modifier/", views.TicketModifierView.as_view(), name="ticket_modifier"),
    path("tickets/<int:pk>/supprimer/", views.TicketSupprimerView.as_view(), name="ticket_supprimer"),
]

# Back-office (administrateur) — préfixe /backoffice/… défini dans config/urls.py
backoffice_urlpatterns = [
    path("", views.BackofficeTicketSupportView.as_view(), name="liste"),
    path("tickets/<int:pk>/", views.BackofficeTicketDetailView.as_view(), name="ticket"),
    path("tickets/<int:pk>/supprimer/", views.BackofficeTicketSupprimerView.as_view(), name="ticket_supprimer"),
    path("moderation/", views.BackofficeModerationView.as_view(), name="moderation"),
    path("moderation/<int:pk>/", views.BackofficeModererMessageView.as_view(), name="moderer"),
]
