"""Permissions du module Flotte — rôles + contrôle par objet."""

from rest_framework.permissions import SAFE_METHODS, BasePermission

from apps.core.roles import Role, est_admin


class EstTransporteur(BasePermission):
    """Écriture réservée aux transporteurs ; les admins passent toujours."""

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if est_admin(user):
            return True
        if request.method in SAFE_METHODS:
            return user.role in {Role.TRANSPORTEUR, Role.PME}
        return user.role == Role.TRANSPORTEUR


class EstAdmin(BasePermission):
    """Réservé au back-office (rôle ADMIN ou superutilisateur)."""

    def has_permission(self, request, view):
        return bool(request.user and est_admin(request.user))


class EstPME(BasePermission):
    """Recherche de trajets réservée aux PME (et aux admins)."""

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and (est_admin(user) or user.role == Role.PME))


class ProprietaireOuAdmin(BasePermission):
    """Un transporteur ne voit et ne modifie QUE sa propre flotte."""

    def has_object_permission(self, request, view, obj):
        if est_admin(request.user):
            return True
        proprietaire = getattr(obj, "transporteur", None) or getattr(obj, "vehicule", None).transporteur
        return proprietaire == request.user
