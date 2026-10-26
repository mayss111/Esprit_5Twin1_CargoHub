"""Scan du QR Code du bon d'expédition.

Le QR Code contient la référence publique du bon. Lire un QR Code
ne crée aucun mouvement : seule la confirmation POST enregistre l'entrée ou la sortie.
Le créneau réservé peut durer une heure. L'arrivée est normale pendant les
2 heures qui suivent son début. Au-delà, un administrateur doit valider
explicitement. Le stockage court de l'entrée réelle à la sortie réelle.
"""

from datetime import timedelta
from urllib.parse import unquote

from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils import timezone

from apps.shipments.models import Expedition
from apps.shipments.services.bon_pdf import lire_jeton
from apps.warehouses.models import CreneauDepot, MouvementColis
from apps.warehouses.services.alerts import prevenir

FENETRE_ARRIVEE = timedelta(hours=2)
ALERTE_AVANT = timedelta(hours=6)
STATUTS_ENTREE = {Expedition.Statut.PUBLIEE, Expedition.Statut.RESERVEE}
STATUTS_REFUSES = {
    Expedition.Statut.ANNULEE,
    Expedition.Statut.REFUSEE,
    Expedition.Statut.BROUILLON,
    Expedition.Statut.A_VERIFIER,
}


def extraire_jeton(texte):
    """Accepte le jeton brut ou l'URL imprimée dans le QR Code."""
    valeur = unquote(str(texte or "")).strip()
    if "/verifier/" in valeur:
        valeur = valeur.split("/verifier/", 1)[1]
        valeur = valeur.split("?", 1)[0].split("#", 1)[0].strip("/")
    return valeur


def _dernier(expedition):
    return (
        MouvementColis.objects.filter(expedition=expedition)
        .select_related("entrepot", "creneau")
        .order_by("-date", "-pk")
        .first()
    )


def _creneau(expedition):
    return (
        CreneauDepot.objects.filter(
            expedition=expedition,
            statut__in=[
                CreneauDepot.Statut.RESERVE,
                CreneauDepot.Statut.DEPOT_DECLARE,
                CreneauDepot.Statut.EFFECTUE,
                CreneauDepot.Statut.TERMINE,
                CreneauDepot.Statut.NO_SHOW,
            ],
        )
        .select_related("entrepot")
        .order_by("-debut")
        .first()
    )


def etat_stockage(entree, maintenant=None):
    maintenant = maintenant or timezone.now()
    limite = entree.date + timedelta(hours=entree.entrepot.duree_stockage_max_heures + entree.prolongation_heures)
    reste = limite - maintenant
    return {
        "limite": limite,
        "duree": maintenant - entree.date,
        "depasse": maintenant > limite,
        "approche": timedelta(0) < reste <= ALERTE_AVANT,
    }


def analyser(jeton, maintenant=None):
    """Identifie l'expédition. N'écrit rien."""
    maintenant = maintenant or timezone.now()
    resultat = {
        "expedition": None,
        "creneau": None,
        "entree": None,
        "erreur": "",
        "peut_entrer": False,
        "peut_sortir": False,
        "hors_creneau": False,
        "stockage": None,
    }
    pk = lire_jeton(extraire_jeton(jeton))
    if pk is None:
        resultat["erreur"] = "QR Code invalide."
        return resultat
    expedition = Expedition.objects.filter(pk=pk).select_related("pme", "adresse_depart", "adresse_arrivee").first()
    if expedition is None:
        resultat["erreur"] = "QR Code invalide."
        return resultat
    resultat["expedition"] = expedition
    if expedition.statut in STATUTS_REFUSES:
        resultat["erreur"] = "Cette expédition ne peut pas être déposée."
        return resultat
    creneau = _creneau(expedition)
    dernier = _dernier(expedition)
    entree = dernier if dernier and dernier.type == MouvementColis.Type.ENTREE else None
    resultat["creneau"] = creneau
    resultat["entree"] = entree
    if entree is not None:
        resultat["peut_sortir"] = True
        resultat["stockage"] = etat_stockage(entree, maintenant)
        return resultat
    if dernier and dernier.type == MouvementColis.Type.SORTIE:
        resultat["erreur"] = "Ce colis est déjà sorti."
        return resultat
    if expedition.statut == Expedition.Statut.LIVREE:
        resultat["erreur"] = "Cette expédition est déjà livrée."
        return resultat
    if creneau is None:
        resultat["erreur"] = "Aucune réservation de dépôt valide."
        return resultat
    if creneau.statut == CreneauDepot.Statut.NO_SHOW:
        resultat["erreur"] = "Cette réservation est classée absente."
        return resultat
    if creneau.statut not in {CreneauDepot.Statut.RESERVE, CreneauDepot.Statut.DEPOT_DECLARE}:
        resultat["erreur"] = "Ce dépôt est déjà terminé."
        return resultat
    if expedition.statut not in STATUTS_ENTREE:
        resultat["erreur"] = "Cette expédition ne peut pas être déposée."
        return resultat
    resultat["peut_entrer"] = True
    resultat["hors_creneau"] = not (creneau.debut <= maintenant <= creneau.debut + FENETRE_ARRIVEE)
    return resultat


def confirmer_entree(jeton, utilisateur, exceptionnel=False, motif="", maintenant=None):
    maintenant = maintenant or timezone.now()
    with transaction.atomic():
        apercu = analyser(jeton, maintenant)
        expedition = apercu["expedition"]
        if expedition is None:
            return None, apercu["erreur"] or "QR Code invalide."
        Expedition.objects.select_for_update().filter(pk=expedition.pk).first()
        list(MouvementColis.objects.select_for_update().filter(expedition=expedition))
        apercu = analyser(jeton, maintenant)
        if not apercu["peut_entrer"]:
            if apercu["entree"] is not None:
                return None, "Une entrée est déjà enregistrée."
            return None, apercu["erreur"] or "L'entrée ne peut pas être enregistrée."
        if apercu["hors_creneau"] and not exceptionnel:
            return None, "Arrivée hors du créneau de 2 heures. Une validation exceptionnelle est requise."
        motif = str(motif or "").strip()
        if apercu["hors_creneau"] and len(motif) < 10:
            return None, "Indiquez un motif d'au moins 10 caractères."
        creneau = apercu["creneau"]
        try:
            with transaction.atomic():
                mouvement = MouvementColis.objects.create(
                    entrepot=creneau.entrepot,
                    expedition=expedition,
                    creneau=creneau,
                    type=MouvementColis.Type.ENTREE,
                    scanne_par=utilisateur,
                    date=maintenant,
                    commentaire=motif,
                    exceptionnel=bool(apercu["hors_creneau"]),
                    ouvert=True,
                )
                creneau.statut = CreneauDepot.Statut.EFFECTUE
                creneau.save(update_fields=["statut", "updated_at"])
        except IntegrityError:
            return None, "Une entrée est déjà enregistrée."
    prevenir(
        expedition.pme,
        "Dépôt confirmé",
        (
            f"L'entrée des marchandises de {expedition.reference} est confirmée à l'entrepôt. "
            "Le volume réservé n'est pas compté une seconde fois."
        ),
        reverse("warehouses:depot", args=[creneau.pk]),
    )
    return mouvement, ""


def confirmer_sortie(jeton, utilisateur, commentaire="", maintenant=None):
    maintenant = maintenant or timezone.now()
    with transaction.atomic():
        apercu = analyser(jeton, maintenant)
        if apercu["expedition"] is None:
            return None, apercu["erreur"] or "QR Code invalide."
        Expedition.objects.select_for_update().filter(pk=apercu["expedition"].pk).first()
        list(MouvementColis.objects.select_for_update().filter(expedition=apercu["expedition"]))
        apercu = analyser(jeton, maintenant)
        if apercu["entree"] is None:
            if apercu["erreur"] == "Ce colis est déjà sorti.":
                return None, apercu["erreur"]
            return None, "Aucune entrée n'est enregistrée."
        entree = (
            MouvementColis.objects.select_for_update()
            .select_related("entrepot", "expedition", "creneau")
            .filter(pk=apercu["entree"].pk, ouvert=True)
            .first()
        )
        if entree is None:
            return None, "Ce colis est déjà sorti."
        mouvement = MouvementColis.objects.create(
            entrepot=entree.entrepot,
            expedition=entree.expedition,
            creneau=entree.creneau,
            type=MouvementColis.Type.SORTIE,
            scanne_par=utilisateur,
            date=maintenant,
            commentaire=str(commentaire or "").strip(),
        )
        entree.ouvert = False
        entree.save(update_fields=["ouvert"])
        if entree.creneau_id and entree.creneau.statut == CreneauDepot.Statut.EFFECTUE:
            entree.creneau.statut = CreneauDepot.Statut.TERMINE
            entree.creneau.save(update_fields=["statut", "updated_at"])
    duree = duree_stockage(entree, mouvement)
    heures = int(duree.total_seconds() // 3600)
    prevenir(
        entree.expedition.pme,
        "Sortie confirmée",
        (
            f"La sortie de {entree.expedition.reference} est enregistrée. "
            f"Durée réelle de stockage : {heures} h. L'espace physique est libéré."
        ),
        reverse("warehouses:depot", args=[entree.creneau_id]) if entree.creneau_id else "",
    )
    return mouvement, ""


def prolonger(mouvement_id, heures, motif):
    motif = str(motif or "").strip()
    try:
        heures = int(heures)
    except (TypeError, ValueError):
        return None, "Indiquez un nombre d'heures."
    if heures < 1 or heures > 168:
        return None, "La prolongation doit être comprise entre 1 et 168 heures."
    if len(motif) < 10:
        return None, "Indiquez un motif d'au moins 10 caractères."
    with transaction.atomic():
        entree = (
            MouvementColis.objects.select_for_update()
            .select_related("entrepot", "expedition")
            .filter(pk=mouvement_id, type=MouvementColis.Type.ENTREE, ouvert=True)
            .first()
        )
        if entree is None:
            return None, "Ce colis n'est plus dans l'entrepôt."
        entree.prolongation_heures += heures
        entree.motif_prolongation = motif
        entree.save(update_fields=["prolongation_heures", "motif_prolongation"])
    return entree, ""


def duree_stockage(entree, sortie):
    return sortie.date - entree.date


def nombre_alertes(maintenant=None):
    maintenant = maintenant or timezone.now()
    total = 0
    entrees = MouvementColis.objects.filter(type=MouvementColis.Type.ENTREE, ouvert=True).select_related("entrepot")
    for entree in entrees:
        etat = etat_stockage(entree, maintenant)
        if etat["depasse"] or etat["approche"]:
            total += 1
    return total
