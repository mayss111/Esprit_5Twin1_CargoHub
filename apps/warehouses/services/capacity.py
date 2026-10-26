"""Capacité réservée des entrepôts.

Une réservation confirmée occupe son volume dès sa création, même si le dépôt
est prévu plus tard. Elle le libère quand sa date de fin est atteinte, ou quand
elle est annulée. Le tableau d'occupation ignore les réservations échues sans
attendre la tâche de clôture.

Le stock confirmé et le dépôt déclaré ne comptent plus à part : tant que la
réservation n'est pas terminée, annulée ou absente, son volume reste réservé.
"""

from decimal import Decimal

from django.db.models import DecimalField, ExpressionWrapper, F, Sum
from django.utils import timezone

from apps.shipments.models import ArticleExpedie
from apps.warehouses.models import CreneauDepot

STATUTS_ACTIFS = (
    CreneauDepot.Statut.RESERVE,
    CreneauDepot.Statut.DEPOT_DECLARE,
    CreneauDepot.Statut.EFFECTUE,
)


def _decimal(valeur):
    if valeur is None:
        return Decimal("0")
    if isinstance(valeur, Decimal):
        return valeur
    return Decimal(str(valeur))


def volume_expedition(expedition):
    total = ArticleExpedie.objects.filter(expedition=expedition).aggregate(
        total=Sum(
            ExpressionWrapper(
                F("volume_m3") * F("quantite"),
                output_field=DecimalField(max_digits=14, decimal_places=3),
            )
        )
    )["total"]
    return _decimal(total)


def volume_ligne(creneau):
    if creneau.volume_reserve is not None:
        return _decimal(creneau.volume_reserve)
    return volume_expedition(creneau.expedition)


def fin_reservation(creneau):
    """Instant où le volume cesse d'être réservé."""
    if creneau.fin_stockage_prevue is not None:
        return creneau.fin_stockage_prevue
    return creneau.fin


def reservations_actives(entrepot, maintenant=None, exclure_expedition_id=None):
    maintenant = maintenant or timezone.now()
    lignes = CreneauDepot.objects.filter(entrepot=entrepot, statut__in=STATUTS_ACTIFS).select_related(
        "expedition", "entrepot"
    )
    if exclure_expedition_id is not None:
        lignes = lignes.exclude(expedition_id=exclure_expedition_id)
    return [creneau for creneau in lignes if fin_reservation(creneau) > maintenant]


def volume_reserve(entrepot, maintenant=None, exclure_expedition_id=None):
    total = Decimal("0")
    for creneau in reservations_actives(entrepot, maintenant, exclure_expedition_id):
        total += volume_ligne(creneau)
    return total


def disponible(entrepot, maintenant=None, exclure_expedition_id=None):
    reste = _decimal(entrepot.capacite_max_m3) - volume_reserve(entrepot, maintenant, exclure_expedition_id)
    if reste < 0:
        return Decimal("0")
    return reste


def peut_accueillir(entrepot, volume, exclure_expedition_id=None, maintenant=None):
    occupe = volume_reserve(entrepot, maintenant, exclure_expedition_id)
    return occupe + _decimal(volume) <= _decimal(entrepot.capacite_max_m3)


def taux_occupation(entrepot, maintenant=None):
    capacite = _decimal(entrepot.capacite_max_m3)
    if capacite <= 0:
        return None
    taux = volume_reserve(entrepot, maintenant) / capacite * Decimal("100")
    if taux < 0:
        taux = Decimal("0")
    return taux.quantize(Decimal("0.001"))


def synthese_entrepot(entrepot, maintenant=None):
    maintenant = maintenant or timezone.now()
    reserve = volume_reserve(entrepot, maintenant)
    capacite = _decimal(entrepot.capacite_max_m3)
    reste = capacite - reserve
    if reste < 0:
        reste = Decimal("0")
    taux = taux_occupation(entrepot, maintenant)
    return {
        "entrepot": entrepot,
        "capacite": capacite,
        "reserve": reserve,
        "disponible": reste,
        "taux": taux,
        "barre": min(taux or Decimal("0"), Decimal("100")),
        "actives": len(reservations_actives(entrepot, maintenant)),
    }


def synthese(nom="", maintenant=None):
    """Totaux des entrepôts actifs. Chaque carte est la somme des lignes."""
    from apps.warehouses.models import Entrepot

    terme = (nom or "").strip()[:80]
    queryset = Entrepot.objects.filter(actif=True)
    if terme:
        queryset = queryset.filter(nom__icontains=terme)
    entrepots = list(queryset.order_by("nom", "ville"))
    lignes = [synthese_entrepot(entrepot, maintenant) for entrepot in entrepots]
    capacite = sum((ligne["capacite"] for ligne in lignes), Decimal("0"))
    reserve = sum((ligne["reserve"] for ligne in lignes), Decimal("0"))
    taux = None
    if capacite > 0:
        taux = (reserve / capacite * Decimal("100")).quantize(Decimal("0.001"))
    return {
        "lignes": lignes,
        "entrepots_actifs": len(entrepots),
        "capacite": capacite,
        "reserve": reserve,
        "disponible": sum((ligne["disponible"] for ligne in lignes), Decimal("0")),
        "taux": taux,
        "actives": sum(ligne["actives"] for ligne in lignes),
    }
