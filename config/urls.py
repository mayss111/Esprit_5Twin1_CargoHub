from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

# (préfixe front-office, préfixe back-office, application)
MODULES = [
    ("comptes/", "utilisateurs/", "accounts"),
    ("messagerie/", "support/", "messaging"),
    ("contrats/", "contrats/", "contracts"),
    ("expeditions/", "expeditions/", "shipments"),
    ("entrepots/", "entrepots/", "warehouses"),
    ("assurance/", "sinistres/", "insurance"),
    ("flotte/", "flotte/", "fleet"),
    ("entretien/", "conformite/", "maintenance"),
    ("ecologie/", "ecologie/", "ecology"),
    ("reservations/", "reservations/", "bookings"),
    ("appels-offres/", "appels-offres/", "tenders"),
    ("suivi/", "incidents/", "tracking"),
    ("paiements/", "paiements/", "payments"),
    ("fidelite/", "fidelite/", "loyalty"),
]

urlpatterns = [
    path("", include("apps.core.urls")),
    path("backoffice/", include("apps.dashboard.urls")),
    path("django-admin/", admin.site.urls),  # outil de développement, pas le back-office final
    # API REST (JWT) — utilisée par le SPA React et le module Matching (M4)
    path("api/token/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("api/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("api/fleet/", include("apps.fleet.api_urls")),
    path("api/admin/", include("apps.fleet.admin_api_urls")),
]

for front, back, app in MODULES:
    module = __import__(f"apps.{app}.urls", fromlist=["urlpatterns", "backoffice_urlpatterns"])
    urlpatterns += [
        path(front, include((module.urlpatterns, app))),
        path(f"backoffice/{back}", include((module.backoffice_urlpatterns, f"bo_{app}"))),
    ]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
