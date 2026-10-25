from django.urls import path

from . import views

# Front-office (PME et transporteurs)
urlpatterns = [
    path("", views.MesSinistresView.as_view(), name="liste"),
    path("nouveau/", views.SinistreCreerView.as_view(), name="creer"),
    path("<int:pk>/", views.SinistreDetailView.as_view(), name="detail"),
    path("<int:pk>/ecouter/", views.SinistreEcouterView.as_view(), name="ecouter"),
    path("<int:pk>/modifier/", views.SinistreModifierView.as_view(), name="modifier"),
    path("<int:pk>/supprimer/", views.SinistreSupprimerView.as_view(), name="supprimer"),
    path("<int:pk>/justificatif/supprimer/", views.PieceJustificativeSupprimerView.as_view(), name="piece_supprimer"),
]

# Back-office (administrateur) — préfixe /backoffice/… défini dans config/urls.py
backoffice_urlpatterns = [
    path("", views.BackofficeSinistreView.as_view(), name="liste"),
    path("<int:pk>/", views.BackofficeSinistreDetailView.as_view(), name="detail"),
    path("<int:pk>/ecouter/", views.SinistreEcouterView.as_view(), name="ecouter"),
]
