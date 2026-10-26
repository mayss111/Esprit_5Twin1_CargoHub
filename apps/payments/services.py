"""Encaissement, facture PDF, commission et remise d’un code promo."""

from decimal import Decimal
from io import BytesIO

from django.conf import settings
from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from apps.bookings.models import Reservation

from .models import Commission, Facture, Paiement

TAUX_COMMISSION = Decimal("0.08")
STATUTS_PAYABLES = (
    Reservation.Statut.ACCEPTEE,
    Reservation.Statut.EN_TRANSIT,
    Reservation.Statut.LIVREE,
)


class PaiementImpossible(Exception):
    pass


def paiements_de(user):
    return Paiement.objects.select_related(
        "reservation__expedition__pme",
        "reservation__trajet__transporteur",
        "facture",
        "commission",
    ).filter(Q(reservation__expedition__pme=user) | Q(reservation__trajet__transporteur=user))


def montant_du(reservation) -> Decimal:
    return reservation.prix_convenu or reservation.trajet.prix_indicatif or Decimal("0")


def assurer_paiement(reservation) -> Paiement:
    if reservation.statut not in STATUTS_PAYABLES:
        raise PaiementImpossible("Le paiement s’ouvre une fois la réservation acceptée.")
    montant = montant_du(reservation)
    if montant <= 0:
        raise PaiementImpossible("Le montant doit être supérieur à 0.")
    paiement, _cree = Paiement.objects.get_or_create(reservation=reservation, defaults={"montant": montant})
    return paiement


def appliquer_code(paiement: Paiement, code: str) -> Paiement:
    if paiement.statut != Paiement.Statut.EN_ATTENTE:
        raise PaiementImpossible("Ce paiement n’est plus modifiable.")
    from apps.loyalty.services import CodeInvalide, calculer_reduction

    base = montant_du(paiement.reservation)
    try:
        reduit, promo = calculer_reduction(base, code, paiement_exclu=paiement.pk)
    except CodeInvalide as exc:
        raise PaiementImpossible(str(exc)) from exc
    paiement.montant = reduit
    paiement.code_promo = promo.code
    paiement.save(update_fields=["montant", "code_promo", "updated_at"])
    return paiement


def rendre_pdf(facture: Facture) -> bytes:
    paiement = facture.paiement
    reservation = paiement.reservation
    buffer = BytesIO()
    page = canvas.Canvas(buffer, pagesize=A4)
    page.setTitle(facture.numero)
    y = 800
    page.setFont("Helvetica-Bold", 16)
    page.drawString(50, y, "CargoHub — Facture")
    page.setFont("Helvetica", 11)
    for ligne in (
        f"Numéro : {facture.numero}",
        f"Date : {timezone.localdate():%d/%m/%Y}",
        f"Réservation : #{reservation.pk}",
        f"PME : {reservation.expedition.pme.email}",
        f"Transporteur : {reservation.trajet.transporteur.email}",
        f"Montant TTC : {paiement.montant} DT",
        f"Code promo : {paiement.code_promo or '—'}",
        f"Statut : {paiement.get_statut_display()}",
    ):
        y -= 22
        page.drawString(50, y, ligne)
    page.showPage()
    page.save()
    return buffer.getvalue()


def _attacher_pdf(facture: Facture) -> Facture:
    if not facture.fichier:
        facture.fichier.save(f"{facture.numero}.pdf", ContentFile(rendre_pdf(facture)), save=True)
    return facture


@transaction.atomic
def encaisser(paiement: Paiement) -> Paiement:
    paiement = Paiement.objects.select_for_update().get(pk=paiement.pk)
    if paiement.statut == Paiement.Statut.PAYE:
        return paiement
    if paiement.statut != Paiement.Statut.EN_ATTENTE:
        raise PaiementImpossible("Ce paiement ne peut pas être encaissé.")
    if paiement.montant <= 0:
        raise PaiementImpossible("Le montant doit être supérieur à 0.")
    paiement.statut = Paiement.Statut.PAYE
    paiement.save(update_fields=["statut", "updated_at"])
    facture, _ = Facture.objects.get_or_create(
        paiement=paiement,
        defaults={"numero": f"CH-{timezone.now():%Y}-{paiement.pk:05d}"},
    )
    _attacher_pdf(facture)
    commission = (paiement.montant * TAUX_COMMISSION).quantize(Decimal("0.01"))
    Commission.objects.get_or_create(
        paiement=paiement,
        defaults={
            "taux": TAUX_COMMISSION,
            "montant_commission": commission,
            "montant_transporteur": (paiement.montant - commission).quantize(Decimal("0.01")),
        },
    )
    from apps.loyalty.services import crediter_paiement

    crediter_paiement(paiement)
    return paiement


@transaction.atomic
def rembourser(paiement: Paiement) -> Paiement:
    paiement = Paiement.objects.select_for_update().get(pk=paiement.pk)
    if paiement.statut != Paiement.Statut.PAYE:
        raise PaiementImpossible("Seul un paiement encaissé peut être remboursé.")
    paiement.statut = Paiement.Statut.REMBOURSE
    paiement.save(update_fields=["statut", "updated_at"])
    from apps.loyalty.services import debiter

    debiter(paiement.reservation.expedition.pme, int(paiement.montant))
    return paiement


def verser_commission(paiement: Paiement) -> Commission:
    commission = getattr(paiement, "commission", None)
    if commission is None or paiement.statut != Paiement.Statut.PAYE:
        raise PaiementImpossible("Aucune commission à verser sur ce paiement.")
    commission.versee = True
    commission.save(update_fields=["versee", "updated_at"])
    return commission


def lancer_checkout(paiement: Paiement, succes_url: str, annulation_url: str) -> str:
    if not settings.STRIPE_SECRET_KEY:
        raise PaiementImpossible("Stripe n’est pas configuré : utilisez le paiement de démonstration.")
    try:
        import stripe

        stripe.api_key = settings.STRIPE_SECRET_KEY
        session = stripe.checkout.Session.create(
            mode="payment",
            client_reference_id=str(paiement.pk),
            line_items=[
                {
                    "quantity": 1,
                    "price_data": {
                        "currency": "eur",
                        "unit_amount": int(paiement.montant * 100),
                        "product_data": {"name": f"CargoHub — réservation #{paiement.reservation_id}"},
                    },
                }
            ],
            success_url=succes_url,
            cancel_url=annulation_url,
            metadata={"paiement_id": str(paiement.pk)},
        )
    except Exception as exc:
        raise PaiementImpossible("Le paiement par carte n’a pas pu démarrer. Réessayez.") from exc
    paiement.stripe_session_id = session.id
    paiement.save(update_fields=["stripe_session_id", "updated_at"])
    return session.url


def confirmer_session(session_id: str) -> Paiement:
    if not settings.STRIPE_SECRET_KEY:
        raise PaiementImpossible("Stripe n’est pas configuré.")
    try:
        import stripe

        stripe.api_key = settings.STRIPE_SECRET_KEY
        session = stripe.checkout.Session.retrieve(session_id)
    except Exception as exc:
        raise PaiementImpossible("Stripe n’a pas confirmé le paiement.") from exc
    if session.payment_status != "paid":
        raise PaiementImpossible("Le paiement par carte n’est pas confirmé.")
    paiement = Paiement.objects.filter(stripe_session_id=session.id).first()
    if paiement is None:
        raise PaiementImpossible("Session de paiement inconnue.")
    return encaisser(paiement)
