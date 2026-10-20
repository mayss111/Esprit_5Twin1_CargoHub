from django.urls import path

from . import views

# Front-office (PME et transporteurs)
urlpatterns = [
    path("", views.MesTrajetsView.as_view(), name="liste"),
    path("vehicules/", views.MesVehiculesView.as_view(), name="vehicules"),
]

# Back-office (administrateur) — préfixe /backoffice/… défini dans config/urls.py
backoffice_urlpatterns = [
    path("", views.BackofficeVehiculeView.as_view(), name="liste"),
]
