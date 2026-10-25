from django.urls import path

from . import views

# Front-office (PME et transporteurs)
urlpatterns = [
    path("", views.MesReservationsView.as_view(), name="liste"),
    path("<int:pk>/", views.ReservationDetailView.as_view(), name="detail"),
    path("<int:pk>/annuler/", views.AnnulerReservationView.as_view(), name="annuler"),
    path("trouver/", views.ExpeditionsAReserverView.as_view(), name="trouver"),
    path("expedition/<int:pk>/camions/", views.CamionsCompatiblesView.as_view(), name="camions"),
    path("expedition/<int:pk>/reserver/<int:trajet_id>/", views.ReserverView.as_view(), name="reserver"),
    path("demandes/", views.DemandesRecuesView.as_view(), name="demandes"),
    path("demandes/<int:pk>/repondre/", views.RepondreDemandeView.as_view(), name="repondre"),
]

# Back-office (administrateur) — préfixe /backoffice/… défini dans config/urls.py
backoffice_urlpatterns = [
    path("", views.BackofficeReservationView.as_view(), name="liste"),
    path("<int:pk>/", views.BackofficeReservationDetailView.as_view(), name="detail"),
    path("<int:pk>/litige/", views.BackofficeAnnulerLitigeView.as_view(), name="litige"),
]
