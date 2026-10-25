"""Réservation d'un créneau de dépôt de 2 heures et d'une fin de réservation.

Le volume est réservé dès la confirmation, jusqu'à la date de fin choisie.
Aucune déclaration de dépôt ni confirmation administrateur n'est demandée.
"""

from datetime import datetime, timedelta

from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils import timezone

from apps.shipments.models import Expedition
from apps.warehouses.models import CreneauDepot, Entrepot
from apps.warehouses.services.alerts import prevenir
from apps.warehouses.services.capacity import disponible, peut_accueillir, volume_expedition, volume_reserve

STATUTS_ELIGIBLES = {Expedition.Statut.PUBLIEE, Expedition.Statut.RESERVEE}
STATUTS_BLOQUANTS = {
    CreneauDepot.Statut.RESERVE,
    CreneauDepot.Statut.DEPOT_DECLARE,
    CreneauDepot.Statut.EFFECTUE,
}
PAS = timedelta(hours=2)


def _identifiant(valeur):
    texte = str(valeur or "").strip()
    if not texte.isdigit():
        return None
    return int(texte)


def _instant(jour, heure):
    return timezone.make_aware(datetime.combine(jour, heure), timezone.get_current_timezone())


def depot_pour_affichage(expedition):
    return (
        expedition.creneaux.filter(statut__in=STATUTS_BLOQUANTS).select_related("entrepot").order_by("-debut").first()
    )


def depot_bloquant(expedition):
    return expedition.creneaux.filter(statut__in=STATUTS_BLOQUANTS).exists()


def expeditions_eligibles(utilisateur):
    return (
        Expedition.objects.filter(
            pme=utilisateur,
            statut__in=STATUTS_ELIGIBLES,
            date_souhaitee__gte=timezone.localdate(),
        )
        .exclude(creneaux__statut__in=STATUTS_BLOQUANTS)
        .select_related("adresse_depart", "adresse_arrivee")
        .prefetch_related("articles")
        .distinct()
        .order_by("-created_at")
    )


def expedition_de(utilisateur, brut):
    """Retourne l'expédition de la PME, ou un message sans divulguer les autres."""
    if not str(brut or "").strip():
        return None, ""
    pk = _identifiant(brut)
    if pk is None:
        return None, "Expédition inconnue."
    expedition = (
        Expedition.objects.filter(pk=pk, pme=utilisateur)
        .select_related("adresse_depart", "adresse_arrivee")
        .prefetch_related("articles")
        .first()
    )
    if expedition is None:
        return None, "Expédition inconnue."
    if expedition.statut not in STATUTS_ELIGIBLES:
        return None, "Cette expédition ne peut pas être déposée."
    return expedition, ""


def parse_date(valeur):
    texte = str(valeur or "").strip()
    if not texte:
        return None, ""
    if len(texte) > 10:
        return None, "Date invalide."
    try:
        return datetime.strptime(texte, "%Y-%m-%d").date(), ""
    except ValueError:
        return None, "Date invalide."


def message_date(expedition, jour):
    aujourd_hui = timezone.localdate()
    if expedition.date_souhaitee < aujourd_hui:
        return "La date de départ est déjà passée. Le dépôt ne peut plus être réservé."
    if jour < aujourd_hui:
        return "La date de dépôt ne peut pas être passée."
    if jour > expedition.date_souhaitee:
        return "Le dépôt doit avoir lieu au plus tard le jour du départ de l'expédition."
    return ""


def creneaux_horaires(entrepot, jour):
    ouverture = _instant(jour, entrepot.horaire_ouverture)
    fermeture = _instant(jour, entrepot.horaire_fermeture)
    if fermeture <= ouverture:
        return []
    creneaux = []
    curseur = ouverture
    while curseur + PAS <= fermeture:
        creneaux.append((curseur, curseur + PAS))
        curseur += PAS
    return creneaux


def _heure(valeur):
    texte = str(valeur or "").strip()
    if len(texte) != 5:
        return None
    try:
        return datetime.strptime(texte, "%H:%M").time()
    except ValueError:
        return None


def parse_fin_reservation(valeur):
    if isinstance(valeur, datetime):
        if timezone.is_naive(valeur):
            return timezone.make_aware(valeur, timezone.get_current_timezone()), ""
        return valeur, ""
    texte = str(valeur or "").strip()
    if not texte:
        return None, "Indiquez la date et l'heure de fin de réservation."
    for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S"):
        try:
            return timezone.make_aware(datetime.strptime(texte, fmt), timezone.get_current_timezone()), ""
        except ValueError:
            continue
    return None, "La date de fin de réservation est invalide."


def lister_creneaux(entrepot, expedition, jour, maintenant=None):
    """Créneaux de dépôt de 2 heures. La capacité est celle des réservations encore actives."""
    maintenant = maintenant or timezone.now()
    if not entrepot.actif:
        return [], "Cet entrepôt n'accepte plus de dépôt."
    erreur = message_date(expedition, jour)
    if erreur:
        return [], erreur
    volume = volume_expedition(expedition)
    if volume <= 0:
        return [], "Le volume de l'expédition n'est pas connu. Aucun dépôt n'est proposé."
    if volume > entrepot.capacite_max_m3:
        return [], (
            f"Le volume de l'expédition ({volume} m³) dépasse la capacité maximale "
            f"de l'entrepôt ({entrepot.capacite_max_m3} m³)."
        )
    if not peut_accueillir(entrepot, volume, expedition.pk, maintenant):
        return [], (
            "La capacité est insuffisante : les réservations actives occupent déjà l'entrepôt "
            f"({entrepot.capacite_max_m3} m³ au maximum)."
        )
    reserve = volume_reserve(entrepot, maintenant, expedition.pk)
    reste = disponible(entrepot, maintenant, expedition.pk)
    disponibles = []
    futur = False
    for debut, fin in creneaux_horaires(entrepot, jour):
        if debut <= maintenant:
            continue
        futur = True
        disponibles.append(
            {
                "debut": debut,
                "fin": fin,
                "valeur": timezone.localtime(debut).strftime("%H:%M"),
                "reserve": reserve,
                "disponible": reste,
            }
        )
    if disponibles:
        return disponibles, ""
    if futur:
        return [], "Aucun créneau ne peut être confirmé pour cette date."
    return [], "Aucun créneau n'est encore disponible ce jour-là."


def _raison_creneau(entrepot, expedition, jour, heure, maintenant):
    for debut, _fin in creneaux_horaires(entrepot, jour):
        if timezone.localtime(debut).time().replace(microsecond=0) == heure:
            if debut <= maintenant:
                return "Ce créneau est déjà passé."
            return "La capacité prévisionnelle de l'entrepôt est insuffisante pour ce dépôt."
    return "Ce créneau est en dehors des horaires d'ouverture."


def reserver(utilisateur, entrepot_id, expedition_id, jour, heure_texte, fin_reservation=None, maintenant=None):
    """Confirme un créneau. Les contrôles sont refaits sous verrou, au moment de l'écriture."""
    maintenant = maintenant or timezone.now()
    heure = _heure(heure_texte)
    fin, erreur_fin = parse_fin_reservation(fin_reservation)
    if jour is None:
        return None, "Choisissez une date de dépôt."
    if heure is None:
        return None, "Choisissez un créneau."
    if erreur_fin:
        return None, erreur_fin

    with transaction.atomic():
        entrepot = Entrepot.objects.select_for_update().filter(pk=entrepot_id).first()
        if entrepot is None or not entrepot.actif:
            return None, "Cet entrepôt n'accepte plus de dépôt."
        expedition, erreur = expedition_de(utilisateur, expedition_id)
        if erreur or expedition is None:
            return None, erreur or "Choisissez une expédition."
        expedition = Expedition.objects.select_for_update().filter(pk=expedition.pk, pme=utilisateur).first()
        if expedition is None or expedition.statut not in STATUTS_ELIGIBLES:
            return None, "Cette expédition ne peut pas être déposée."
        if depot_bloquant(expedition):
            return None, "Cette expédition a déjà un dépôt réservé."
        list(
            CreneauDepot.objects.select_for_update().filter(
                entrepot=entrepot,
                statut__in=STATUTS_BLOQUANTS,
            )
        )
        disponibles, erreur = lister_creneaux(entrepot, expedition, jour, maintenant)
        if erreur:
            return None, erreur
        choisi = next((slot for slot in disponibles if slot["valeur"] == heure.strftime("%H:%M")), None)
        if choisi is None:
            return None, _raison_creneau(entrepot, expedition, jour, heure, maintenant)
        if fin <= choisi["debut"]:
            return None, "La fin de réservation doit être postérieure au début du dépôt."
        if fin <= maintenant:
            return None, "La fin de réservation doit être dans le futur."
        volume = volume_expedition(expedition)
        if volume <= 0:
            return None, "Le volume de l'expédition n'est pas connu. Aucun dépôt n'est proposé."
        if not peut_accueillir(entrepot, volume, expedition.pk, maintenant):
            return None, (
                "La capacité est insuffisante : les réservations actives occupent déjà l'entrepôt "
                f"({entrepot.capacite_max_m3} m³ au maximum)."
            )
        try:
            with transaction.atomic():
                creneau = CreneauDepot.objects.create(
                    entrepot=entrepot,
                    expedition=expedition,
                    debut=choisi["debut"],
                    fin=choisi["fin"],
                    volume_reserve=volume,
                    fin_stockage_prevue=fin,
                    statut=CreneauDepot.Statut.RESERVE,
                )
        except IntegrityError:
            return None, "Cette expédition a déjà un dépôt réservé."
    prevenir(
        expedition.pme,
        "Réservation de dépôt confirmée",
        message_reservation(creneau),
        reverse("warehouses:depot", args=[creneau.pk]),
    )
    return creneau, ""


def annuler(creneau_id, utilisateur, motif="", admin=False):
    with transaction.atomic():
        creneau = (
            CreneauDepot.objects.select_for_update()
            .select_related("expedition__pme", "entrepot")
            .filter(pk=creneau_id)
            .first()
        )
        if creneau is None or (not admin and creneau.expedition.pme_id != utilisateur.id):
            return None, "Réservation inconnue."
        if creneau.statut == CreneauDepot.Statut.EFFECTUE:
            return None, "Un dépôt déjà confirmé ne peut pas être annulé."
        if creneau.statut == CreneauDepot.Statut.DEPOT_DECLARE and not admin:
            return None, "Le dépôt est déjà déclaré. Seul un administrateur peut annuler cette réservation."
        if creneau.statut not in {CreneauDepot.Statut.RESERVE, CreneauDepot.Statut.DEPOT_DECLARE}:
            return None, "Ce dépôt ne peut plus être annulé."
        if admin:
            motif = str(motif or "").strip()
            if len(motif) < 10:
                return None, "Indiquez un motif d'au moins 10 caractères."
        else:
            motif = "Annulée par la PME."
        creneau.statut = CreneauDepot.Statut.ANNULE
        creneau.motif_annulation = motif
        creneau.save(update_fields=["statut", "motif_annulation", "updated_at"])
    prevenir(
        creneau.expedition.pme,
        "Réservation de dépôt annulée",
        f"La réservation {creneau.reference} est annulée. L'espace de {creneau.volume_reserve or 0} m³ est libéré.",
        reverse("warehouses:depot", args=[creneau.pk]),
    )
    return creneau, ""


def message_reservation(creneau):
    debut = timezone.localtime(creneau.debut)
    fin = timezone.localtime(creneau.fin)
    fin_reservee = timezone.localtime(creneau.fin_stockage_prevue) if creneau.fin_stockage_prevue else fin
    return (
        f"Votre réservation a été confirmée. Un espace de {creneau.volume_reserve} m³ a été réservé "
        f"dans l'entrepôt {creneau.entrepot.nom}, pour le dépôt du {debut:%d/%m/%Y} "
        f"de {debut:%H:%M} à {fin:%H:%M}, jusqu'au {fin_reservee:%d/%m/%Y} à {fin_reservee:%H:%M}."
    )
