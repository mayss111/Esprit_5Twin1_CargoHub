"""Routes API back-office — préfixe /api/admin/ (config/urls.py)."""

from rest_framework.routers import DefaultRouter

from . import api

router = DefaultRouter()
router.register("facteurs-emission", api.FacteurEmissionViewSet, basename="admin-facteur-emission")

urlpatterns = router.urls
