"""Middleware HTTP partagé pour la langue explicite de l'interface."""

from django.utils import translation

from .html_langue import traduire_page
from .traductions import LANGUES


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
