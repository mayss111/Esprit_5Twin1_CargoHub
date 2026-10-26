"""Routes API du module Flotte — préfixe /api/fleet/ (config/urls.py)."""

from rest_framework.routers import DefaultRouter

from . import api

router = DefaultRouter()
router.register("vehicules", api.VehiculeViewSet, basename="vehicule")
router.register("trajets", api.TrajetViewSet, basename="trajet")
router.register("entretiens", api.EntretienViewSet, basename="entretien")
router.register("facteurs-emission", api.FacteurEmissionViewSet, basename="facteur-emission")

urlpatterns = router.urls
