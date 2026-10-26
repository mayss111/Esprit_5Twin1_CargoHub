from celery import shared_task

from .ai import resumer_avis
from .models import Avis, ResumeTransporteur


@shared_task
def calculer_resume(transporteur_id: int):
    """Le résumé des avis appelle un LLM (1 à 3 s) : il est calculé hors de la requête HTTP."""
    resume, _ = ResumeTransporteur.objects.get_or_create(transporteur_id=transporteur_id)
    avis = list(Avis.objects.filter(cible_id=transporteur_id))
    try:
        resume.texte = resumer_avis(avis)
    except Exception:
        resume.texte = "Le résumé n’a pas pu être calculé. Réessayez dans un instant."
    resume.en_cours = False
    resume.save(update_fields=["texte", "en_cours", "updated_at"])
