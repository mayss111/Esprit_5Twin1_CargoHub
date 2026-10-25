"""Routes Django (serveur) du module Flotte — front-office transporteur.

Les routes API REST sont dans api_urls.py (préfixe /api/fleet/).
"""

from django.urls import path

from . import views

# Front-office (transporteur)
urlpatterns = [
    path("", views.MesTrajetsView.as_view(), name="liste"),
    path("assistant-ia/", views.OptimiseurIATransportView.as_view(), name="optimiseur-ia"),
    path("vehicules/", views.MesVehiculesView.as_view(), name="vehicules"),
    path("vehicules/ajouter/", views.CreerVehiculeView.as_view(), name="vehicule-creer"),
    path("vehicules/<int:pk>/modifier/", views.ModifierVehiculeView.as_view(), name="vehicule-modifier"),
    path("vehicules/<int:pk>/supprimer/", views.SupprimerVehiculeView.as_view(), name="vehicule-supprimer"),
    path("vehicules/<int:pk>/documents/", views.AjouterDocumentView.as_view(), name="vehicule-document"),
    path("vehicules/<int:pk>/certificat/", views.CertificatVertView.as_view(), name="vehicule-certificat"),
    path("impact/", views.ImpactEcologiqueView.as_view(), name="impact"),
    path("trajets/publier/", views.PublierTrajetView.as_view(), name="trajet-publier"),
    path("trajets/<int:pk>/modifier/", views.ModifierTrajetView.as_view(), name="trajet-modifier"),
    path("trajets/<int:pk>/annuler/", views.AnnulerTrajetView.as_view(), name="trajet-annuler"),
]

# Back-office (administrateur) — préfixe /backoffice/… défini dans config/urls.py
backoffice_urlpatterns = [
    path("", views.BackofficeVehiculeView.as_view(), name="liste"),
    path("trajets/", views.BackofficeTrajetView.as_view(), name="trajets"),
    path("vehicules/<int:pk>/<str:decision>/", views.ValiderVehiculeView.as_view(), name="vehicule-valider"),
]
