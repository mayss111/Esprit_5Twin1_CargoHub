from django.urls import path

from . import views

urlpatterns = [
    path("", views.MesPaiementsView.as_view(), name="liste"),
    path("reservation/<int:pk>/", views.OuvrirPaiementView.as_view(), name="ouvrir"),
    path("stripe/retour/", views.RetourStripeView.as_view(), name="stripe_retour"),
    path("<int:pk>/", views.PaiementDetailView.as_view(), name="detail"),
    path("<int:pk>/facture/", views.FactureView.as_view(), name="facture"),
]

backoffice_urlpatterns = [
    path("", views.BackofficePaiementView.as_view(), name="liste"),
    path("<int:pk>/", views.BackofficePaiementDetailView.as_view(), name="detail"),
]
