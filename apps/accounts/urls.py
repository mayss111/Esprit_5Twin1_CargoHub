from django.urls import path

from . import views

urlpatterns = [
    path("inscription/", views.InscriptionView.as_view(), name="inscription"),
    path("connexion/", views.ConnexionView.as_view(), name="connexion"),
    path("deconnexion/", views.DeconnexionView.as_view(), name="deconnexion"),
    path("profil/", views.ProfilView.as_view(), name="profil"),
    path("profil/modifier/", views.ModifierProfilView.as_view(), name="profil_modifier"),
    path("profil/desactiver/", views.DesactiverCompteView.as_view(), name="desactiver"),
    path("mot-de-passe/oublie/", views.MotDePasseOublieView.as_view(), name="mot_de_passe_oublie"),
    path("mot-de-passe/envoye/", views.MotDePasseEnvoyeView.as_view(), name="mot_de_passe_envoye"),
    path(
        "mot-de-passe/reinitialiser/<uidb64>/<token>/",
        views.ReinitialiserMotDePasseView.as_view(),
        name="reinitialiser_mot_de_passe",
    ),
    path("mot-de-passe/termine/", views.ReinitialisationTermineeView.as_view(), name="reinitialisation_terminee"),
]

backoffice_urlpatterns = [
    path("", views.BackofficeUtilisateursView.as_view(), name="liste"),
    path("<int:pk>/", views.BackofficeUtilisateurDetailView.as_view(), name="detail"),
    path("<int:pk>/modifier/", views.BackofficeUtilisateurModifierView.as_view(), name="modifier"),
    path("<int:pk>/validation/", views.BackofficeValiderTransporteurView.as_view(), name="valider"),
    path("<int:pk>/supprimer/", views.BackofficeUtilisateurSupprimerView.as_view(), name="supprimer"),
]
