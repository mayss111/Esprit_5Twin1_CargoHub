from django.http import HttpResponse
from django.views.generic import ListView, TemplateView

from apps.accounts.reliability import score_fiabilite
from apps.core.roles import Role
from .mixins import AdminRequiredMixin, RoleRequiredMixin


def sante(request):
    """Utilisé par Render et Docker pour vérifier que l'application tourne."""
    return HttpResponse("ok")


class AccueilView(TemplateView):
    template_name = "core/accueil.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        context["fiabilite_accueil"] = (
            score_fiabilite(user)
            if user.is_authenticated and user.role in {Role.PME, Role.TRANSPORTEUR}
            else None
        )
        return context


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
