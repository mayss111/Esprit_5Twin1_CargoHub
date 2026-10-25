from django.urls import path

from . import views

urlpatterns = [
    path("", views.SuiviView.as_view(), name="liste"),
    path("<int:pk>/", views.SuiviDetailView.as_view(), name="detail"),
    path("incident/<int:pk>/modifier/", views.IncidentModifierView.as_view(), name="incident_modifier"),
    path("incident/<int:pk>/supprimer/", views.IncidentSupprimerView.as_view(), name="incident_supprimer"),
    path("avis/<int:pk>/modifier/", views.AvisModifierView.as_view(), name="avis_modifier"),
    path("avis/<int:pk>/supprimer/", views.AvisSupprimerView.as_view(), name="avis_supprimer"),
]

backoffice_urlpatterns = [
    path("", views.BackofficeIncidentView.as_view(), name="liste"),
    path("<int:pk>/", views.BackofficeIncidentDetailView.as_view(), name="detail"),
]
