from celery import shared_task

from apps.fleet.services import verifier_conformite_flotte


@shared_task
def verifier_conformite():
    """M3 — bloque les véhicules non conformes (documents ou contrôle technique expirés) et réactive les autres."""
    bloques, reactives = verifier_conformite_flotte()
    return {"bloques": bloques, "reactives": reactives}
