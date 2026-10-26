"""Middleware HTTP partagé — CORS pour le SPA React (Vite :5173)."""

from django.http import HttpResponse
from django.utils import translation

from .html_langue import traduire_page
from .traductions import LANGUES

ORIGINES_SPA = (
    "http://localhost:5173",
    "http://127.0.0.1:5173",
)


class CorsSpaMiddleware:
    """Autorise le SPA Vite à appeler /api/ (préflight OPTIONS + en-têtes CORS)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        origine = request.headers.get("Origin")
        if request.method == "OPTIONS" and origine in ORIGINES_SPA:
            reponse = HttpResponse()
        else:
            reponse = self.get_response(request)
        if origine in ORIGINES_SPA:
            reponse["Access-Control-Allow-Origin"] = origine
            reponse["Access-Control-Allow-Credentials"] = "true"
            reponse["Access-Control-Allow-Headers"] = "Authorization, Content-Type, Accept"
            reponse["Access-Control-Allow-Methods"] = "GET, POST, PUT, PATCH, DELETE, OPTIONS"
            reponse["Access-Control-Max-Age"] = "86400"
        return reponse


class LangueExpliciteMiddleware:
    """Active FR, EN ou AR seulement si la personne l'a choisi."""

    COOKIE = "cargohub_langue"

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        code = request.COOKIES.get(self.COOKIE, "fr")
        if code not in LANGUES:
            code = "fr"
        translation.activate(code)
        request.LANGUAGE_CODE = code
        reponse = self.get_response(request)
        if code != "fr":
            traduire_page(reponse, code)
        reponse.headers["Content-Language"] = code
        return reponse
