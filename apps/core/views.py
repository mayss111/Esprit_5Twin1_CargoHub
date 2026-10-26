from django.http import HttpResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.generic import ListView, TemplateView

from .mixins import AdminRequiredMixin, RoleRequiredMixin
from .traductions import LANGUES


def choisir_langue(request):
    """Enregistre FR, EN ou AR. Le choix est ignoré s'il vient seulement du navigateur."""
    code = request.POST.get("langue", "fr")
    if code not in LANGUES:
        code = "fr"
    suivant = request.POST.get("next") or reverse("core:accueil")
    if not url_has_allowed_host_and_scheme(suivant, allowed_hosts={request.get_host()}):
        suivant = reverse("core:accueil")
    reponse = redirect(suivant)
    reponse.set_cookie(
        "cargohub_langue",
        code,
        max_age=60 * 60 * 24 * 365,
        samesite="Lax",
        secure=request.is_secure(),
    )
    return reponse


def sante(request):
    """Utilisé par Render et Docker pour vérifier que l'application tourne."""
    return HttpResponse("ok")


class AccueilView(TemplateView):
    template_name = "core/accueil.html"


class ListeFrontView(RoleRequiredMixin, ListView):
    """
    Page « liste » du front-office, réutilisable par toutes les apps.

    Dans votre app, héritez-en et définissez :
        model, roles, titre, colonnes = [("champ", "Libellé"), ...]
        get_queryset()  -> seulement les objets de l'utilisateur connecté
    Remplacez ensuite `template_name` par votre propre gabarit quand la page grandit.
    """

    template_name = "core/liste.html"
    paginate_by = 20
    titre = ""
    sous_titre = ""
    colonnes: list[tuple[str, str]] = []
    bouton = None  # (libellé, nom d'URL) pour un bouton « Ajouter »

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(titre=self.titre, sous_titre=self.sous_titre, colonnes=self.colonnes, bouton=self.bouton)
        return ctx


class ListeBackofficeView(AdminRequiredMixin, ListeFrontView):
    """Même principe pour le back-office (tous les objets, réservé aux admins)."""

    template_name = "backoffice/liste.html"
