from django.contrib.auth import get_user_model

from .tasks import notifier


def notifier_dossier(dossier, titre, message, lien="", *, lien_admin="", administrateurs=False, exclure=()):
    """Notifie les parties réellement liées à une réclamation ou un sinistre."""
    utilisateur_ids = {dossier.auteur_id}
    utilisateur_ids.add(getattr(dossier, "partie_mise_en_cause_id", None))
    expedition = getattr(dossier, "expedition_effective", None) or getattr(dossier, "expedition", None)
    if expedition:
        utilisateur_ids.add(expedition.pme_id)
        utilisateur_ids.update(expedition.reservations.values_list("trajet__transporteur_id", flat=True))
    administrateur_ids = set()
    if administrateurs:
        administrateur_ids.update(
            get_user_model()
            .objects.filter(is_active=True)
            .filter(role="ADMIN")
            .values_list("pk", flat=True)
        )
        administrateur_ids.update(
            get_user_model().objects.filter(is_superuser=True, is_active=True).values_list("pk", flat=True)
        )
        utilisateur_ids.update(administrateur_ids)

    for utilisateur_id in utilisateur_ids - set(exclure):
        if utilisateur_id:
            notifier.delay(
                utilisateur_id,
                titre,
                message,
                lien_admin if utilisateur_id in administrateur_ids and lien_admin else lien,
            )
