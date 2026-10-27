from django.urls import path

from . import views

# Front-office (transporteurs)
urlpatterns = [
    path("", views.MesTrajetsView.as_view(), name="liste"),
    path("trajets/nouveau/", views.TrajetCreerView.as_view(), name="trajet_creer"),
    path("trajets/<int:pk>/modifier/", views.TrajetModifierView.as_view(), name="trajet_modifier"),
    path("trajets/<int:pk>/annuler/", views.TrajetAnnulerView.as_view(), name="trajet_annuler"),
    path("vehicules/", views.MesVehiculesView.as_view(), name="vehicules"),
    path("vehicules/nouveau/", views.VehiculeCreerView.as_view(), name="vehicule_creer"),
    path("vehicules/<int:pk>/modifier/", views.VehiculeModifierView.as_view(), name="vehicule_modifier"),
    path("vehicules/<int:pk>/supprimer/", views.VehiculeSupprimerView.as_view(), name="vehicule_supprimer"),
    path("vehicules/<int:pk>/document/", views.DocumentAjouterView.as_view(), name="document_ajouter"),
    path("vehicules/<int:pk>/certificat-vert/", views.CertificatVertView.as_view(), name="certificat"),
    path("impact/", views.ImpactView.as_view(), name="impact"),
    path("planificateur/", views.PlanificateurView.as_view(), name="planificateur"),
]

# Back-office (administrateur) — préfixe /backoffice/… défini dans config/urls.py
backoffice_urlpatterns = [
    path("", views.BackofficeVehiculeView.as_view(), name="liste"),
    path("vehicules/<int:pk>/decision/", views.BackofficeVehiculeDecisionView.as_view(), name="decision"),
    path("trajets/", views.BackofficeTrajetView.as_view(), name="trajets"),
]
