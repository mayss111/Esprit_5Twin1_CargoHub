from django.urls import path

from . import views

urlpatterns = [
    path("notifications/<int:pk>/", views.OuvrirNotificationView.as_view(), name="notification"),
    path("", views.MesExpeditionsView.as_view(), name="liste"),
    path("historique/", views.HistoriqueExpeditionsView.as_view(), name="historique"),
    path("nouvelle/", views.CreerExpeditionView.as_view(), name="creer"),
    path("importer/", views.ImporterExpeditionsView.as_view(), name="importer"),
    path("assistant/", views.AssistantSaisieView.as_view(), name="assistant"),
    path("verifier/<str:jeton>/", views.VerifierBonView.as_view(), name="verifier"),
    path("<int:pk>/bon/", views.BonExpeditionView.as_view(), name="bon"),
    path("<int:pk>/", views.DetailExpeditionView.as_view(), name="detail"),
    path("<int:pk>/modifier/", views.ModifierExpeditionView.as_view(), name="modifier"),
    path("<int:pk>/annuler/", views.AnnulerExpeditionView.as_view(), name="annuler"),
    path("<int:pk>/supprimer/", views.SupprimerExpeditionView.as_view(), name="supprimer"),
]

backoffice_urlpatterns = [
    path("", views.BackofficeExpeditionView.as_view(), name="liste"),
    path("verifications/", views.BackofficeVerificationsView.as_view(), name="verifications"),
    path(
        "verifications/<int:pk>/decision/",
        views.BackofficeVerificationDecisionView.as_view(),
        name="verification_decision",
    ),
    path("interdictions/", views.BackofficeInterdictionsView.as_view(), name="interdictions"),
    path("interdictions/nouvelle/", views.BackofficeInterdictionCreerView.as_view(), name="interdiction_creer"),
    path(
        "interdictions/<int:pk>/modifier/",
        views.BackofficeInterdictionModifierView.as_view(),
        name="interdiction_modifier",
    ),
    path("<int:pk>/", views.BackofficeDetailExpeditionView.as_view(), name="detail"),
]
