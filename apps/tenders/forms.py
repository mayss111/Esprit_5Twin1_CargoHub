from decimal import Decimal

from django import forms
from django.db.models import DecimalField, ExpressionWrapper, F, Sum
from django.utils import timezone

from apps.bookings.models import Reservation
from apps.bookings.services import EXPEDITION_VIDE, est_compatible
from apps.fleet.models import Trajet
from apps.shipments.models import Expedition

from .models import AppelOffre, Offre

TRAJET_INCOMPATIBLE = "Ce trajet part trop loin de la date souhaitée ou ne passe pas par les bonnes villes."


RESERVATIONS_BLOQUANTES = [Reservation.Statut.EN_ATTENTE, Reservation.Statut.ACCEPTEE, Reservation.Statut.EN_TRANSIT]
EXPEDITION_INDISPONIBLE = "Cette expédition ne peut pas faire l’objet d’un appel d’offres."


def expeditions_pour_appel(pme):
    """
    Expéditions de la PME pour lesquelles un appel d'offres a un sens :
    publiées, avec de la marchandise (poids > 0), qui partent APRÈS aujourd'hui (pour qu'une date limite
    future et antérieure à l'expédition soit possible), sans réservation en cours et sans appel d'offres.
    """
    poids = ExpressionWrapper(
        F("articles__poids_kg") * F("articles__quantite"), output_field=DecimalField(max_digits=12, decimal_places=2)
    )
    en_cours = Reservation.objects.filter(statut__in=RESERVATIONS_BLOQUANTES).values("expedition_id")
    return (
        Expedition.objects.filter(
            pme=pme,
            statut=Expedition.Statut.PUBLIEE,
            date_souhaitee__gt=timezone.localdate(),
            appel_offre__isnull=True,  # une expédition n'a qu'UN appel d'offres (OneToOne), même clos
        )
        .exclude(pk__in=en_cours)
        .annotate(poids=Sum(poids))
        .filter(poids__gt=0)
        .select_related("adresse_depart", "adresse_arrivee")
        .order_by("date_souhaitee")
    )


def pourquoi_indisponible(expedition):
    """Raison, en français simple, pour laquelle cette expédition n'est pas proposée (None si elle l'est)."""
    if expedition.statut != Expedition.Statut.PUBLIEE:
        return f"elle n’est pas publiée ({expedition.get_statut_display().lower()})"
    if expedition.poids_total_kg <= 0:
        return "elle n’a aucune marchandise (0 kg)"
    if expedition.date_souhaitee <= timezone.localdate():
        return "elle part aujourd’hui ou est déjà passée : plus le temps de recevoir des offres"
    if expedition.reservations.filter(statut__in=RESERVATIONS_BLOQUANTES).exists():
        return "elle a déjà une réservation en cours"
    if AppelOffre.objects.filter(expedition=expedition).exists():
        return "elle a déjà un appel d’offres"
    return None


class AppelOffreForm(forms.ModelForm):
    class Meta:
        model = AppelOffre
        fields = ("expedition", "date_cloture", "prix_max")
        labels = {
            "expedition": "Expédition",
            "date_cloture": "Date limite des offres",
            "prix_max": "Budget maximum (DT)",
        }
        help_texts = {
            "date_cloture": "Après cette date, plus aucune offre n’est acceptée.",
            "prix_max": "Les transporteurs voient ce budget.",
        }
        widgets = {
            "date_cloture": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
            "prix_max": forms.NumberInput(attrs={"min": "1", "step": "0.01"}),
        }

    def __init__(self, *args, pme, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["prix_max"].required = True
        # Validation côté navigateur, cohérente avec clean_date_cloture() : pas de date limite passée.
        self.fields["date_cloture"].widget.attrs["min"] = timezone.localtime().strftime("%Y-%m-%dT%H:%M")
        self.pme = pme
        if self.instance.pk:
            del self.fields["expedition"]  # on ne change pas l'expédition d'un appel existant
        else:
            champ = self.fields["expedition"]
            champ.queryset = expeditions_pour_appel(pme)
            champ.empty_label = "Choisissez une expédition publiée"
            champ.error_messages["invalid_choice"] = EXPEDITION_INDISPONIBLE

    def clean_date_cloture(self):
        date = self.cleaned_data["date_cloture"]
        if date <= timezone.now():
            raise forms.ValidationError("La date limite doit être dans le futur.")
        return date

    def clean_prix_max(self):
        prix = self.cleaned_data["prix_max"]
        if prix is None or prix <= 0:
            raise forms.ValidationError("Le budget doit être supérieur à 0.")
        return prix

    def clean(self):
        data = super().clean()
        expedition = data.get("expedition") or getattr(self.instance, "expedition", None)
        date = data.get("date_cloture")
        # Côté serveur, même si quelqu'un force un identifiant dans le POST : on revérifie toutes les règles.
        if "expedition" in self.fields and expedition and (raison := pourquoi_indisponible(expedition)):
            self.add_error("expedition", f"{EXPEDITION_INDISPONIBLE} Raison : {raison}.")
            return data
        if expedition and expedition.poids_total_kg <= 0:
            self.add_error("expedition" if "expedition" in self.fields else None, EXPEDITION_VIDE)
        if expedition and date and date.date() > expedition.date_souhaitee:
            self.add_error("date_cloture", "La date limite doit être avant la date d’expédition.")
        return data


class OffreForm(forms.ModelForm):
    class Meta:
        model = Offre
        fields = ("trajet", "prix", "message")
        labels = {"trajet": "Votre trajet", "prix": "Votre prix (DT)", "message": "Message à la PME (facultatif)"}
        widgets = {
            "prix": forms.NumberInput(attrs={"min": "1", "step": "0.01"}),
            "message": forms.Textarea(attrs={"rows": 3, "maxlength": 1000}),
        }

    def __init__(self, *args, transporteur, appel, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.appel = appel
        self.instance.transporteur = transporteur
        ouverts = (
            Trajet.objects.filter(
                transporteur=transporteur, statut=Trajet.Statut.OUVERT, date_depart__gte=timezone.now()
            )
            .select_related("vehicule")
            .prefetch_related("etapes")
        )
        # Seuls les trajets qui conviennent à l'expédition (villes, date ± 2 jours, place) sont proposés.
        compatibles = [t.pk for t in ouverts if est_compatible(appel.expedition, t)]
        self.a_des_trajets_ouverts = bool(ouverts)
        champ = self.fields["trajet"]
        champ.required = True
        champ.queryset = Trajet.objects.filter(pk__in=compatibles).prefetch_related("etapes").order_by("date_depart")
        champ.empty_label = "Choisissez un de vos trajets compatibles"
        champ.error_messages["invalid_choice"] = TRAJET_INCOMPATIBLE
        champ.help_text = "Seuls vos trajets qui passent par les bonnes villes, à ± 2 jours de la date, sont proposés."

    def clean_trajet(self):
        trajet = self.cleaned_data["trajet"]
        if not est_compatible(self.instance.appel.expedition, trajet):
            raise forms.ValidationError(TRAJET_INCOMPATIBLE)
        return trajet

    def clean_prix(self):
        prix = self.cleaned_data["prix"]
        if prix <= Decimal("0"):
            raise forms.ValidationError("Le prix doit être supérieur à 0.")
        return prix

    def clean(self):
        data = super().clean()
        appel, transporteur = self.instance.appel, self.instance.transporteur
        if not appel.est_ouvert:
            raise forms.ValidationError("Cet appel d’offres est clos : il n’accepte plus d’offre.")
        if Offre.objects.filter(appel=appel, transporteur=transporteur).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("Vous avez déjà fait une offre sur cet appel : modifiez-la plutôt.")
        return data
