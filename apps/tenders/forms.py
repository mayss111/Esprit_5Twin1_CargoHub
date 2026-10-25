from decimal import Decimal

from django import forms
from django.utils import timezone

from apps.bookings.models import Reservation
from apps.bookings.services import EXPEDITION_VIDE, est_compatible
from apps.fleet.models import Trajet
from apps.shipments.models import Expedition

from .models import AppelOffre, Offre

TRAJET_INCOMPATIBLE = "Ce trajet part trop loin de la date souhaitée ou ne passe pas par les bonnes villes."


def expeditions_pour_appel(pme):
    """Expéditions publiées de la PME, sans transporteur déjà trouvé ni appel d'offres, et pas encore parties
    (date souhaitée aujourd'hui ou plus tard : une date limite dans le futur reste possible)."""
    deja_attribuees = Reservation.objects.filter(
        statut__in=[Reservation.Statut.ACCEPTEE, Reservation.Statut.EN_TRANSIT, Reservation.Statut.LIVREE]
    ).values("expedition_id")
    return (
        Expedition.objects.filter(
            pme=pme,
            statut=Expedition.Statut.PUBLIEE,
            appel_offre__isnull=True,  # une expédition n'a qu'un seul appel d'offres (OneToOne)
            date_souhaitee__gte=timezone.localdate(),
        )
        .exclude(pk__in=deja_attribuees)
        .select_related("adresse_depart", "adresse_arrivee")
    )


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
        if self.instance.pk:
            del self.fields["expedition"]  # on ne change pas l'expédition d'un appel existant
        else:
            self.fields["expedition"].queryset = expeditions_pour_appel(pme)
            self.fields["expedition"].empty_label = "Choisissez une expédition publiée"

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
