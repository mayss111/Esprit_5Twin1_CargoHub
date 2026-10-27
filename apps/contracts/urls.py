from django.urls import path

from . import views

# Front-office (PME et transporteurs)
urlpatterns = [
    path("", views.MesContratsView.as_view(), name="liste"),
    path("generer/<int:reservation_id>/", views.GenererContratView.as_view(), name="generer"),
    path("<int:pk>/", views.ContratDetailView.as_view(), name="detail"),
    path("<int:pk>/signer/", views.SignerContratView.as_view(), name="signer"),
    path("<int:pk>/pdf/", views.ContratPdfView.as_view(), name="pdf"),
    path("<int:pk>/supprimer/", views.ContratSupprimerView.as_view(), name="supprimer"),
    path("documents/<int:pk>/supprimer/", views.DocumentSupprimerView.as_view(), name="document_supprimer"),
]

# Back-office (administrateur) — préfixe /backoffice/… défini dans config/urls.py
backoffice_urlpatterns = [
    path("", views.BackofficeContratView.as_view(), name="liste"),
    path("<int:pk>/", views.BackofficeContratDetailView.as_view(), name="detail"),
    path("<int:pk>/pdf/", views.BackofficeContratPdfView.as_view(), name="pdf"),
    path("<int:pk>/supprimer/", views.BackofficeContratSupprimerView.as_view(), name="supprimer"),
]
