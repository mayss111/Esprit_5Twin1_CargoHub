from django.urls import path

from . import views

urlpatterns = [
    path("", views.FideliteView.as_view(), name="liste"),
]

backoffice_urlpatterns = [
    path("", views.BackofficeCodePromoView.as_view(), name="liste"),
    path("nouveau/", views.CodePromoCreerView.as_view(), name="creer"),
    path("<int:pk>/modifier/", views.CodePromoModifierView.as_view(), name="modifier"),
    path("<int:pk>/supprimer/", views.CodePromoSupprimerView.as_view(), name="supprimer"),
]
