"""
Contrôle d'accès par rôle, utilisé par TOUTES les applications.

Front-office :  RoleRequiredMixin avec roles = [Role.PME] ou [Role.TRANSPORTEUR]
Back-office  :  AdminRequiredMixin (réservé aux administrateurs)
"""

from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin

from .roles import est_admin


class RoleRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Autorise seulement les rôles listés dans `roles` (les admins passent toujours)."""

    roles: list[str] = []

    def test_func(self):
        user = self.request.user
        return est_admin(user) or (not self.roles or user.role in self.roles)


class AdminRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Pages du back-office."""

    def test_func(self):
        return est_admin(self.request.user)
