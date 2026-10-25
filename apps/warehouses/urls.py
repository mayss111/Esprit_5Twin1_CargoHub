from django.urls import path

from . import views, views_depots, views_import, views_occupation, views_scan

urlpatterns = [
    path("", views.PointsRelaisView.as_view(), name="liste"),
    path("depots/", views_depots.MesDepotsView.as_view(), name="mes_depots"),
    path("depots/<int:pk>/", views_depots.DetailDepotView.as_view(), name="depot"),
    path("depots/<int:pk>/annuler/", views_depots.AnnulerDepotView.as_view(), name="depot_annuler"),
    path("<int:pk>/", views.DetailPointRelaisView.as_view(), name="detail"),
    path("<int:pk>/reserver/", views_depots.ReserverDepotView.as_view(), name="reserver"),
]

backoffice_urlpatterns = [
    path("", views.BackofficeEntrepotView.as_view(), name="liste"),
    path("nouveau/", views.BackofficeCreerEntrepotView.as_view(), name="creer"),
    path("importer/", views_import.BackofficeImporterEntrepotsView.as_view(), name="importer"),
    path("importer/modele/", views_import.ModeleImportEntrepotsView.as_view(), name="importer_modele"),
    path("reservations/", views_depots.BackofficeReservationsView.as_view(), name="reservations"),
    path("occupation/", views_occupation.BackofficeOccupationView.as_view(), name="occupation"),
    path(
        "occupation/chiffres/",
        views_occupation.BackofficeOccupationChiffresView.as_view(),
        name="occupation_chiffres",
    ),
    path("reservations/<int:pk>/", views_depots.BackofficeDetailReservationView.as_view(), name="reservation"),
    path(
        "reservations/<int:pk>/annuler/",
        views_depots.BackofficeAnnulerReservationView.as_view(),
        name="reservation_annuler",
    ),
    path("scanner/", views_scan.ScannerView.as_view(), name="scanner"),
    path("mouvements/", views_scan.MouvementsView.as_view(), name="mouvements"),
    path("mouvements/<int:pk>/prolonger/", views_scan.ProlongerStockageView.as_view(), name="prolonger"),
    path("<int:pk>/", views.BackofficeDetailEntrepotView.as_view(), name="detail"),
    path("<int:pk>/modifier/", views.BackofficeModifierEntrepotView.as_view(), name="modifier"),
    path("<int:pk>/desactiver/", views.BackofficeDesactiverEntrepotView.as_view(), name="desactiver"),
    path("<int:pk>/activer/", views.BackofficeActiverEntrepotView.as_view(), name="activer"),
]
