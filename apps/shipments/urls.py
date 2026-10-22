from django.urls import path

from . import views

urlpatterns = [
    path("", views.MesExpeditionsView.as_view(), name="liste"),
    path("historique/", views.HistoriqueExpeditionsView.as_view(), name="historique"),
    path("nouvelle/", views.CreerExpeditionView.as_view(), name="creer"),
    path("<int:pk>/", views.DetailExpeditionView.as_view(), name="detail"),
    path("<int:pk>/modifier/", views.ModifierExpeditionView.as_view(), name="modifier"),
    path("<int:pk>/annuler/", views.AnnulerExpeditionView.as_view(), name="annuler"),
    path("<int:pk>/supprimer/", views.SupprimerExpeditionView.as_view(), name="supprimer"),
]

backoffice_urlpatterns = [
    path("", views.BackofficeExpeditionView.as_view(), name="liste"),
    path("<int:pk>/", views.BackofficeDetailExpeditionView.as_view(), name="detail"),
]
