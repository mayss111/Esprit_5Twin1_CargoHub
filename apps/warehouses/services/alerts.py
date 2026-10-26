"""Notifications de dépôt. Réutilise la tâche déjà présente dans les réservations."""


def prevenir(utilisateur, titre, message, lien=""):
    from django.core.mail import send_mail

    from apps.bookings.models import Notification

    if utilisateur is None:
        return
    if Notification.objects.filter(destinataire=utilisateur, titre=titre, message=message).exists():
        return
    try:
        from apps.bookings.tasks import notifier

        notifier.delay(utilisateur.pk, titre, message, lien)
    except Exception:
        Notification.objects.create(destinataire=utilisateur, titre=titre, message=message, lien=lien)
        send_mail(f"[CargoHub] {titre}", message, None, [utilisateur.email], fail_silently=True)
