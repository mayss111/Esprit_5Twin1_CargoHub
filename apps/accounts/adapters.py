"""Réglages de django-allauth, utilisé uniquement pour la connexion Google (voir settings ACCOUNT_ADAPTER)."""

from allauth.account.adapter import DefaultAccountAdapter
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter

from .double_auth import url_double_auth_si_requise


class CompteAdapter(DefaultAccountAdapter):
    def is_open_for_signup(self, request):
        # L'inscription par email passe par accounts:inscription (création du profil PME / transporteur).
        return False

    def get_login_redirect_url(self, request):
        url = super().get_login_redirect_url(request)
        return url_double_auth_si_requise(request.user, url) or url


class CompteGoogleAdapter(DefaultSocialAccountAdapter):
    def is_open_for_signup(self, request, sociallogin):
        return True
