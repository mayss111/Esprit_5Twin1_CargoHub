"""Formulaires de planification assistée de la flotte."""

from datetime import timedelta
from decimal import Decimal

from django import forms
from django.utils import timezone


class PlanificationIAForm(forms.Form):
    ville_depart = forms.CharField(
        label="Ville de départ",
        max_length=80,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Sousse"}),
    )
    ville_arrivee = forms.CharField(
        label="Ville d'arrivée",
        max_length=80,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Tunis"}),
    )
    date_depart = forms.DateField(
        label="Date prévue",
        initial=lambda: timezone.localdate() + timedelta(days=1),
        widget=forms.DateInput(attrs={"class": "form-control", "type": "date"}),
    )
    poids_kg = forms.DecimalField(
        label="Poids à transporter (kg)",
        min_value=Decimal("0.01"),
        max_digits=10,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0.01"}),
    )
    volume_m3 = forms.DecimalField(
        label="Volume à transporter (m³)",
        min_value=Decimal("0.001"),
        max_digits=8,
        decimal_places=3,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.001", "min": "0.001"}),
    )
    distance_km = forms.DecimalField(
        label="Distance estimée (km)",
        min_value=Decimal("1"),
        max_value=Decimal("5000"),
        max_digits=7,
        decimal_places=1,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "1", "min": "1", "max": "5000"}),
    )

    def clean_date_depart(self):
        date_depart = self.cleaned_data["date_depart"]
        if date_depart < timezone.localdate():
            raise forms.ValidationError("La date de départ doit être aujourd'hui ou plus tard.")
        return date_depart

    def clean(self):
        cleaned_data = super().clean()
        depart = cleaned_data.get("ville_depart", "").strip()
        arrivee = cleaned_data.get("ville_arrivee", "").strip()
        if depart and arrivee and depart.casefold() == arrivee.casefold():
            self.add_error("ville_arrivee", "La ville d'arrivée doit différer de la ville de départ.")
        return cleaned_data
