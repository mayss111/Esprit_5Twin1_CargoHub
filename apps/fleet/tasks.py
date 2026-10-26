@shared_task
def notifier_alerte_documents():
    """Notification + email : documents qui expirent dans les 30 jours."""
    limite = timezone.localdate() + timedelta(days=JOURS_ALERTE_EXPIRATION)
    alertes = 0
    for doc in DocumentVehicule.objects.filter(
        date_expiration__lte=limite,
        date_expiration__gte=timezone.localdate(),
    ).select_related("vehicule__transporteur"):
        services.notifier(  # notification dans l'application + email
            doc.vehicule.transporteur,
            "Document bientôt expiré",
            f"{doc.get_type_display()} du véhicule {doc.vehicule.immatriculation} "
            f"expire le {doc.date_expiration:%d/%m/%Y}. Pensez à le renouveler.",
            reverse("fleet:vehicules"),
        )
        alertes += 1
    return alertes


@shared_task
def notifier_alerte_entretien():
    """Rappel des entretiens dont la prochaine échéance arrive (module Entretien)."""
    limite = timezone.localdate() + timedelta(days=7)
    rappels = 0
    for entretien in Entretien.objects.filter(
        prochaine_echeance__lte=limite,
    ).select_related("vehicule__transporteur"):
        services.notifier(
            entretien.vehicule.transporteur,
            "Entretien à prévoir",
            f"{entretien.vehicule} : entretien « {entretien.type} » "
            f"à prévoir avant le {entretien.prochaine_echeance:%d/%m/%Y}.",
            reverse("maintenance:liste"),
        )
        rappels += 1
    return rappels


@shared_task
def generer_certificat_vert(vehicule_id=None, transporteur_id=None, periode_debut=None, periode_fin=None):
    """Génère un certificat vert (PDF). Le résultat est renvoyé au module Fidélité (M5)."""
    from apps.accounts.models import Utilisateur

    if not transporteur_id:
        transporteur_id = Vehicule.objects.get(pk=vehicule_id).transporteur_id
    transporteur = Utilisateur.objects.get(pk=transporteur_id)
    periode_fin = periode_fin or timezone.localdate()
    periode_debut = periode_debut or periode_fin - timedelta(days=365)
    contenu, bilan = services.generer_certificat_vert(transporteur, periode_debut, periode_fin)
    return {"octets": len(contenu), **bilan}
