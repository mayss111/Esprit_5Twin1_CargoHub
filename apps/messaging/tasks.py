from celery import shared_task

from .ai import repondre_support
from .models import TicketSupport


@shared_task
def repondre_ticket(ticket_id: int):
    """L'appel au LLM prend 1 à 3 s : il est fait en arrière-plan et le résultat est enregistré sur le ticket."""
    ticket = TicketSupport.objects.filter(pk=ticket_id).first()
    if not ticket or ticket.reponse_ia:
        return
    ticket.reponse_ia = repondre_support(f"{ticket.sujet}\n\n{ticket.description}")
    ticket.save(update_fields=["reponse_ia", "updated_at"])
