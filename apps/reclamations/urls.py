from django.urls import path

from . import views

app_name = "reclamations"

urlpatterns = [
    path("", views.MesReclamationsView.as_view(), name="liste"),
    path("nouvelle/", views.ReclamationCreerView.as_view(), name="creer"),
    path("<int:pk>/", views.ReclamationDetailView.as_view(), name="detail"),
    path("<int:pk>/ecouter/", views.ReclamationEcouterView.as_view(), name="ecouter"),
    path("<int:pk>/modifier/", views.ReclamationModifierView.as_view(), name="modifier"),
    path("<int:pk>/annuler/", views.ReclamationAnnulerView.as_view(), name="annuler"),
]

backoffice_urlpatterns = [
    path("", views.BackofficeReclamationsView.as_view(), name="liste"),
    path("<int:pk>/", views.BackofficeReclamationDetailView.as_view(), name="detail"),
    path("<int:pk>/ecouter/", views.ReclamationEcouterView.as_view(), name="ecouter"),
]
