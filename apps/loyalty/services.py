"""Points, codes promo et récompense de parrainage."""

from decimal import Decimal

from django.db.models import Q
from django.utils import timezone

from apps.accounts.models import Utilisateur

from .models import CodePromo, Parrainage, PointsFidelite

POINTS_PARRAIN = 50


class CodeInvalide(Exception):
    pass


class ParrainageImpossible(Exception):
    pass


def compte_points(utilisateur) -> PointsFidelite:
    compte, _ = PointsFidelite.objects.get_or_create(utilisateur=utilisateur)
    return compte


def crediter(utilisateur, points: int) -> PointsFidelite:
    compte = compte_points(utilisateur)
    if points > 0:
        compte.solde += int(points)
        compte.save(update_fields=["solde", "updated_at"])
    return compte


def debiter(utilisateur, points: int) -> PointsFidelite:
    compte = compte_points(utilisateur)
    compte.solde = max(0, compte.solde - int(points))
    compte.save(update_fields=["solde", "updated_at"])
    return compte


def crediter_paiement(paiement):
    """1 point par dinar payé pour la PME, et 50 points au parrain au premier paiement."""
    pme = paiement.reservation.expedition.pme
    crediter(pme, int(paiement.montant))
    parrainage = Parrainage.objects.filter(filleul=pme, recompense_versee=False).first()
    if parrainage:
        crediter(parrainage.parrain, POINTS_PARRAIN)
        parrainage.recompense_versee = True
        parrainage.save(update_fields=["recompense_versee", "updated_at"])


def calculer_reduction(montant: Decimal, code: str, paiement_exclu=None):
    from apps.payments.models import Paiement

    promo = CodePromo.objects.filter(code__iexact=(code or "").strip()).first()
    if promo is None or not promo.actif:
        raise CodeInvalide("Ce code promo n’existe pas ou n’est plus actif.")
    if promo.date_expiration and promo.date_expiration < timezone.localdate():
        raise CodeInvalide("Ce code promo a expiré.")
    if montant < promo.montant_minimum:
        raise CodeInvalide("Le montant est inférieur au minimum exigé par ce code.")
    if promo.usage_unique:
        deja = Paiement.objects.filter(code_promo__iexact=promo.code).exclude(statut=Paiement.Statut.ECHOUE)
        if paiement_exclu:
            deja = deja.exclude(pk=paiement_exclu)
        if deja.exists():
            raise CodeInvalide("Ce code a déjà été utilisé.")
    if promo.type == CodePromo.Type.POURCENTAGE:
        nouveau = (montant * (Decimal("100") - promo.valeur) / Decimal("100")).quantize(Decimal("0.01"))
    else:
        nouveau = (montant - promo.valeur).quantize(Decimal("0.01"))
    if nouveau <= 0:
        raise CodeInvalide("La réduction ne peut pas annuler tout le montant.")
    return nouveau, promo


def parrainer(filleul, email: str) -> Parrainage:
    if Parrainage.objects.filter(filleul=filleul).exists():
        raise ParrainageImpossible("Vous avez déjà un parrain.")
    parrain = Utilisateur.objects.filter(email__iexact=email.strip()).exclude(pk=filleul.pk).first()
    if parrain is None:
        if Utilisateur.objects.filter(Q(email__iexact=email.strip()), pk=filleul.pk).exists():
            raise ParrainageImpossible("Vous ne pouvez pas vous parrainer vous-même.")
        raise ParrainageImpossible("Aucun compte ne correspond à cet email.")
    return Parrainage.objects.create(parrain=parrain, filleul=filleul)


def codes_disponibles():
    aujourd = timezone.localdate()
    return CodePromo.objects.filter(actif=True).filter(
        Q(date_expiration__isnull=True) | Q(date_expiration__gte=aujourd)
    )
