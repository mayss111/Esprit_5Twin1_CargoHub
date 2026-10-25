"""Gestionnaire d'erreurs commun à toute l'API REST — réponses JSON standardisées en français."""

import logging

from rest_framework import status
from rest_framework.views import exception_handler

logger = logging.getLogger("cargohub.api")


def gestion_erreurs(exc, contexte):
    """Traduit les erreurs DRF et les ValueError métier en réponse JSON homogène."""
    from rest_framework.response import Response

    # Erreurs métier levées par les services / perform_create (ValueError, PermissionError)
    if isinstance(exc, ValueError):
        return Response({"detail": str(exc)}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)
    if isinstance(exc, PermissionError):
        return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)

    reponse = exception_handler(exc, contexte)
    if reponse is None:
        return None
    # Erreurs de validation (400) remontées en 422 — code commun pour "entrée invalide"
    if reponse.status_code == 400:
        reponse.status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    # Uniformise : tout est sous "detail" ou "erreurs" { champ: [messages] }
    if isinstance(reponse.data, dict) and "detail" in reponse.data:
        detail = str(reponse.data["detail"])
    elif isinstance(reponse.data, list):
        detail = " ; ".join(str(e) for e in reponse.data)
        reponse.data = {"detail": detail}
    else:
        reponse.data = {"erreurs": {cle: (v if isinstance(v, list) else [str(v)]) for cle, v in reponse.data.items()}}
    return reponse
