from django.urls import path

from . import views

# Front-office (PME et transporteurs)
urlpatterns = [
    path("", views.MesContratsView.as_view(), name="liste"),
]

# Back-office (administrateur) — préfixe /backoffice/… défini dans config/urls.py
backoffice_urlpatterns = [
    path("", views.BackofficeContratView.as_view(), name="liste"),
]
