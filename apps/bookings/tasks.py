from celery import shared_task
from django.contrib.auth import get_user_model
from django.core.mail import send_mail

from .models import Notification


@shared_task
def notifier(utilisateur_id: int, titre: str, message: str, lien: str = ""):
    """Notification dans l'application + email (exécutée en arrière-plan par Celery)."""
    user = get_user_model().objects.filter(pk=utilisateur_id).first()
    if not user:
        return
    Notification.objects.create(destinataire=user, titre=titre, message=message, lien=lien)
    send_mail(f"[CargoHub] {titre}", message, None, [user.email], fail_silently=True)
