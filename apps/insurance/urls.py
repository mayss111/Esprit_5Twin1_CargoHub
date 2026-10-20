from django.urls import path

from . import views

# Front-office (PME et transporteurs)
urlpatterns = [
    path("", views.MesAssurancesView.as_view(), name="liste"),
]

# Back-office (administrateur) — préfixe /backoffice/… défini dans config/urls.py
backoffice_urlpatterns = [
    path("", views.BackofficeSinistreView.as_view(), name="liste"),
]
