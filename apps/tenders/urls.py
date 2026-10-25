from django.urls import path

from . import views

# Front-office (PME et transporteurs)
urlpatterns = [
    path("", views.AppelsOffresView.as_view(), name="liste"),
    path("nouveau/", views.AppelCreerView.as_view(), name="creer"),
    path("<int:pk>/", views.AppelDetailView.as_view(), name="detail"),
    path("<int:pk>/modifier/", views.AppelModifierView.as_view(), name="modifier"),
    path("<int:pk>/supprimer/", views.AppelSupprimerView.as_view(), name="supprimer"),
    path("<int:pk>/offre/", views.OffreCreerView.as_view(), name="offre_creer"),
    path("offre/<int:pk>/modifier/", views.OffreModifierView.as_view(), name="offre_modifier"),
    path("offre/<int:pk>/retirer/", views.OffreRetirerView.as_view(), name="offre_retirer"),
    path("offre/<int:pk>/retenir/", views.RetenirOffreView.as_view(), name="retenir"),
    path("<int:pk>/aide-au-choix/", views.LancerRecommandationView.as_view(), name="recommander"),
    path("<int:pk>/aide-au-choix/statut/", views.StatutRecommandationView.as_view(), name="recommandation_statut"),
    path("suggestion-prix/", views.SuggestionPrixView.as_view(), name="suggestion_prix"),
]

# Back-office (administrateur) — préfixe /backoffice/… défini dans config/urls.py
backoffice_urlpatterns = [
    path("", views.BackofficeAppelOffreView.as_view(), name="liste"),
    path("<int:pk>/", views.BackofficeAppelDetailView.as_view(), name="detail"),
]
