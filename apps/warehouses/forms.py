"""Formulaire administrateur d'un entrepôt."""

import re
from decimal import Decimal

from django import forms
from django.core.validators import MaxValueValidator, MinValueValidator

from apps.shipments.forms import GOUVERNORATS

from .models import Entrepot

NOM = re.compile(r"[0-9A-Za-zÀ-ÿ][0-9A-Za-zÀ-ÿ' -]{2,119}\Z")
VILLE = re.compile(r"[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ' -]{1,79}\Z")
ADRESSE = re.compile(r"[0-9A-Za-zÀ-ÿ][0-9A-Za-zÀ-ÿ' .,/-]{4,254}\Z")


class EntrepotForm(forms.ModelForm):
    gouvernorat = forms.ChoiceField(
        label="Gouvernorat",
        choices=[("", "Choisir un gouvernorat"), *GOUVERNORATS],
        error_messages={"required": "Choisissez un gouvernorat."},
    )
    horaire_ouverture = forms.TimeField(
        label="Ouverture",
        input_formats=["%H:%M", "%H:%M:%S"],
        widget=forms.TimeInput(
            format="%H:%M",
            attrs={"type": "time", "class": "form-control form-control-sm", "required": True},
        ),
    )
    horaire_fermeture = forms.TimeField(
        label="Fermeture",
        input_formats=["%H:%M", "%H:%M:%S"],
        widget=forms.TimeInput(
            format="%H:%M",
            attrs={"type": "time", "class": "form-control form-control-sm", "required": True},
        ),
    )

    class Meta:
        model = Entrepot
        fields = (
            "nom",
            "description",
            "adresse",
            "ville",
            "gouvernorat",
            "code_postal",
            "latitude",
            "longitude",
            "capacite_max_m3",
            "horaire_ouverture",
            "horaire_fermeture",
            "duree_stockage_max_heures",
            "delai_grace_minutes",
            "actif",
        )
        widgets = {
            "nom": forms.TextInput(
                attrs={
                    "class": "form-control form-control-sm",
                    "required": True,
                    "minlength": "3",
                    "maxlength": "120",
                    "pattern": r"[0-9A-Za-zÀ-ÿ][0-9A-Za-zÀ-ÿ' \-]{2,119}",
                }
            ),
            "description": forms.Textarea(
                attrs={"class": "form-control form-control-sm", "rows": 2, "required": True, "minlength": "10"}
            ),
            "adresse": forms.TextInput(
                attrs={
                    "class": "form-control form-control-sm",
                    "required": True,
                    "minlength": "5",
                    "maxlength": "255",
                }
            ),
            "ville": forms.TextInput(
                attrs={
                    "class": "form-control form-control-sm",
                    "required": True,
                    "minlength": "2",
                    "maxlength": "80",
                    "pattern": r"[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ' \-]{1,79}",
                }
            ),
            "code_postal": forms.TextInput(
                attrs={
                    "class": "form-control form-control-sm",
                    "required": True,
                    "minlength": "4",
                    "maxlength": "4",
                    "pattern": r"\d{4}",
                    "inputmode": "numeric",
                }
            ),
            "latitude": forms.NumberInput(
                attrs={
                    "class": "form-control form-control-sm",
                    "step": "any",
                    "min": "-90",
                    "max": "90",
                    "required": True,
                }
            ),
            "longitude": forms.NumberInput(
                attrs={
                    "class": "form-control form-control-sm",
                    "step": "any",
                    "min": "-180",
                    "max": "180",
                    "required": True,
                }
            ),
            "capacite_max_m3": forms.NumberInput(
                attrs={
                    "class": "form-control form-control-sm",
                    "step": "0.001",
                    "min": "0.001",
                    "max": "99999.999",
                    "required": True,
                }
            ),
            "actif": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }
        labels = {
            "nom": "Nom de l'entrepôt",
            "description": "Description",
            "adresse": "Adresse",
            "ville": "Ville",
            "code_postal": "Code postal",
            "latitude": "Latitude",
            "longitude": "Longitude",
            "capacite_max_m3": "Capacité maximale (m³)",
            "actif": "Entrepôt actif",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["gouvernorat"].widget.attrs.update({"class": "form-select form-select-sm", "required": True})
        self.fields["description"].required = True
        self.fields["description"].error_messages["required"] = "Décrivez l'entrepôt en au moins 10 caractères."
        self.fields["code_postal"].required = True
        self.fields["code_postal"].error_messages["required"] = "Indiquez le code postal."
        self.fields["latitude"].required = True
        self.fields["latitude"].error_messages["required"] = "Indiquez la latitude."
        self._bornes(self.fields["latitude"], -90, 90, "La latitude doit être comprise entre -90 et 90.")
        self.fields["longitude"].required = True
        self.fields["longitude"].error_messages["required"] = "Indiquez la longitude."
        self._bornes(self.fields["longitude"], -180, 180, "La longitude doit être comprise entre -180 et 180.")
        self.fields["nom"].error_messages["required"] = "Indiquez le nom de l'entrepôt."
        self.fields["adresse"].error_messages["required"] = "Indiquez l'adresse."
        self.fields["ville"].error_messages["required"] = "Indiquez la ville."
        self.fields["capacite_max_m3"].error_messages["required"] = "Indiquez la capacité maximale."
        self.fields["duree_stockage_max_heures"].required = False
        self.fields["duree_stockage_max_heures"].widget.attrs.update(
            {"class": "form-control form-control-sm", "min": "1"}
        )
        self.fields["delai_grace_minutes"].required = False
        self.fields["delai_grace_minutes"].widget.attrs.update({"class": "form-control form-control-sm", "min": "0"})

    def clean_nom(self):
        nom = (self.cleaned_data.get("nom") or "").strip()
        if not NOM.fullmatch(nom):
            raise forms.ValidationError(
                "Indiquez un nom d'au moins 3 caractères : lettres, chiffres, espaces ou traits d'union."
            )
        return nom

    def clean_description(self):
        description = (self.cleaned_data.get("description") or "").strip()
        if len(description) < 10:
            raise forms.ValidationError("Décrivez l'entrepôt en au moins 10 caractères.")
        return description

    def clean_adresse(self):
        adresse = (self.cleaned_data.get("adresse") or "").strip()
        if not ADRESSE.fullmatch(adresse):
            raise forms.ValidationError("Indiquez une adresse d'au moins 5 caractères.")
        return adresse

    def clean_ville(self):
        ville = (self.cleaned_data.get("ville") or "").strip()
        if not VILLE.fullmatch(ville):
            raise forms.ValidationError("Indiquez une ville d'au moins 2 lettres, sans chiffre.")
        return ville

    def clean_code_postal(self):
        code = (self.cleaned_data.get("code_postal") or "").strip()
        if not re.fullmatch(r"\d{4}", code):
            raise forms.ValidationError("Le code postal tunisien comporte 4 chiffres.")
        return code

    def clean_duree_stockage_max_heures(self):
        valeur = self.cleaned_data.get("duree_stockage_max_heures")
        if not valeur:
            return 48
        return valeur

    def clean_delai_grace_minutes(self):
        valeur = self.cleaned_data.get("delai_grace_minutes")
        if valeur is None:
            return 30
        return valeur

    def clean_capacite_max_m3(self):
        capacite = self.cleaned_data["capacite_max_m3"]
        if capacite > Decimal("99999.999"):
            raise forms.ValidationError("La capacité ne peut pas dépasser 99999.999 m³.")
        if not self.instance.pk:
            return capacite
        stocke = self.instance.volume_present_m3()
        if stocke is not None and capacite < stocke:
            raise forms.ValidationError("La capacité ne peut pas être inférieure au volume actuellement stocké.")
        return capacite

    @staticmethod
    def _bornes(champ, minimum, maximum, message):
        champ.validators = [
            validateur
            for validateur in champ.validators
            if not isinstance(validateur, (MinValueValidator, MaxValueValidator))
        ]
        champ.validators.extend([MinValueValidator(minimum, message), MaxValueValidator(maximum, message)])


class ImportEntrepotsForm(forms.Form):
    fichier = forms.FileField(
        label="Fichier CSV ou Excel",
        widget=forms.ClearableFileInput(
            attrs={
                "class": "form-control",
                "accept": ".csv,.xlsx",
            }
        ),
    )

    def clean_fichier(self):
        fichier = self.cleaned_data["fichier"]
        nom = (fichier.name or "").lower()
        if not nom.endswith((".csv", ".xlsx")):
            raise forms.ValidationError("Utilisez un fichier .csv ou .xlsx.")
        if fichier.size > 2 * 1024 * 1024:
            raise forms.ValidationError("Le fichier dépasse 2 Mo.")
        return fichier


class AnnulationDepotForm(forms.Form):
    motif = forms.CharField(
        label="Motif d'annulation",
        min_length=10,
        max_length=500,
        widget=forms.Textarea(attrs={"rows": 3, "class": "form-control", "required": True}),
        error_messages={"min_length": "Indiquez un motif d'au moins 10 caractères."},
    )
