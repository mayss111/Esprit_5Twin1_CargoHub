from decimal import Decimal

from django import forms
from django.utils import timezone

from apps.fleet.models import Trajet
from apps.shipments.models import Expedition

from .models import AppelOffre, Offre


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
        if self.instance.pk:
            del self.fields["expedition"]  # on ne change pas l'expédition d'un appel existant
        else:
            self.fields["expedition"].queryset = Expedition.objects.filter(
                pme=pme, statut=Expedition.Statut.PUBLIEE, appel_offre__isnull=True
            ).select_related("adresse_depart", "adresse_arrivee")
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
        self.fields["trajet"].required = True
        self.fields["trajet"].queryset = Trajet.objects.filter(
            transporteur=transporteur, statut=Trajet.Statut.OUVERT, date_depart__gte=timezone.now()
        ).order_by("date_depart")
        self.fields["trajet"].empty_label = "Choisissez un de vos trajets ouverts"

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
