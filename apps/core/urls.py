from django.urls import path

from . import views

app_name = "core"
urlpatterns = [
    path("", views.AccueilView.as_view(), name="accueil"),
    path("sante/", views.sante, name="sante"),
]
