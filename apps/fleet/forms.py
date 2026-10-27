from datetime import timedelta
from decimal import Decimal

from django import forms
from django.db.models import Max
from django.utils import timezone

from .models import DocumentVehicule, EtapeTrajet, Trajet, Vehicule
from .validation import erreur_fichier_vehicule

STATUTS_ACTIFS = [Trajet.Statut.OUVERT, Trajet.Statut.COMPLET, Trajet.Statut.EN_COURS]


class VehiculeForm(forms.ModelForm):
    class Meta:
        model = Vehicule
        fields = ("type", "immatriculation", "capacite_kg", "capacite_m3")
        labels = {
            "type": "Type de véhicule",
            "immatriculation": "Immatriculation",
            "capacite_kg": "Capacité (kg)",
            "capacite_m3": "Volume (m³)",
        }
        widgets = {
            "capacite_kg": forms.NumberInput(attrs={"min": "1"}),
            "capacite_m3": forms.NumberInput(attrs={"min": "0.01", "step": "0.01"}),
        }

    def clean_immatriculation(self):
        return self.cleaned_data["immatriculation"].strip().upper()

    def clean(self):
        data = super().clean()
        if not self.instance.pk:
            return data
        # On ne réduit pas la capacité sous celle d'un trajet encore actif.
        utilise = self.instance.trajets.filter(statut__in=STATUTS_ACTIFS).aggregate(
            poids=Max("capacite_totale_kg"), volume=Max("capacite_totale_m3")
        )
        if data.get("capacite_kg") and utilise["poids"] and data["capacite_kg"] < utilise["poids"]:
            self.add_error("capacite_kg", "La capacité ne peut pas être inférieure à celle d’un trajet actif.")
        if data.get("capacite_m3") and utilise["volume"] and data["capacite_m3"] < utilise["volume"]:
            self.add_error("capacite_m3", "Le volume ne peut pas être inférieur à celui d’un trajet actif.")
        return data


class DocumentVehiculeForm(forms.ModelForm):
    class Meta:
        model = DocumentVehicule
        fields = ("type", "date_expiration", "fichier")
        labels = {"type": "Document", "date_expiration": "Expire le", "fichier": "Fichier (PDF, JPEG ou PNG)"}
        widgets = {
            "date_expiration": forms.DateInput(attrs={"type": "date"}),
            "fichier": forms.FileInput(attrs={"accept": ".pdf,image/jpeg,image/png"}),
        }

    def __init__(self, *args, vehicule, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.vehicule = vehicule
        self.fields["date_expiration"].widget.attrs["min"] = (timezone.localdate() + timedelta(days=1)).isoformat()

    def clean_date_expiration(self):
        date = self.cleaned_data["date_expiration"]
        if date <= timezone.localdate():
            raise forms.ValidationError("La date d’expiration doit être dans le futur.")
        return date

    def clean_fichier(self):
        fichier = self.cleaned_data["fichier"]
        erreur = erreur_fichier_vehicule(fichier)
        if erreur:
            raise forms.ValidationError(erreur)
        return fichier

    def validate_unique(self):
        pass  # un nouveau document remplace l'ancien du même type (voir la vue)


class TrajetForm(forms.ModelForm):
    """Publier ou modifier un trajet. La place proposée est plafonnée au véhicule et à ce qui est déjà réservé."""

    etapes = forms.CharField(
        label="Villes étapes (facultatif)",
        required=False,
        help_text="Séparées par des virgules, dans l’ordre du trajet. Ex. : Sousse, Hammamet",
    )

    class Meta:
        model = Trajet
        fields = (
            "vehicule",
            "ville_depart",
            "ville_arrivee",
            "date_depart",
            "capacite_totale_kg",
            "capacite_totale_m3",
            "distance_km",
            "prix_indicatif",
            "recurrent",
        )
        labels = {
            "vehicule": "Véhicule",
            "ville_depart": "Ville de départ",
            "ville_arrivee": "Ville d’arrivée",
            "date_depart": "Date et heure de départ",
            "capacite_totale_kg": "Place proposée (kg)",
            "capacite_totale_m3": "Place proposée (m³)",
            "distance_km": "Distance (km)",
            "prix_indicatif": "Prix indicatif (DT)",
            "recurrent": "Répéter ce trajet chaque semaine",
        }
        help_texts = {
            "capacite_totale_kg": "",
            "distance_km": "Sert au calcul du CO₂ et à la suggestion de prix des appels d’offres.",
        }
        widgets = {
            "date_depart": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
            "capacite_totale_kg": forms.NumberInput(attrs={"min": "0.01", "step": "0.01"}),
            "capacite_totale_m3": forms.NumberInput(attrs={"min": "0.001", "step": "0.001"}),
            "distance_km": forms.NumberInput(attrs={"min": "1"}),
            "prix_indicatif": forms.NumberInput(attrs={"min": "0", "step": "0.01"}),
        }

    def __init__(self, *args, transporteur, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.transporteur = transporteur
        champ = self.fields["vehicule"]
        champ.queryset = Vehicule.objects.filter(transporteur=transporteur, statut=Vehicule.Statut.ACTIF, conforme=True)
        champ.empty_label = "Choisissez un véhicule actif et conforme"
        for nom in ("capacite_totale_kg", "capacite_totale_m3", "distance_km"):
            self.fields[nom].required = True
        self.fields["date_depart"].widget.attrs["min"] = timezone.localtime().strftime("%Y-%m-%dT%H:%M")
        if self.instance.pk:
            self.initial["etapes"] = ", ".join(e.ville for e in self.instance.etapes.all())
            # Trajet créé avant la « place proposée » : on repart de la place libre + la part déjà réservée.
            if self.instance.capacite_totale_kg is None:
                self.initial["capacite_totale_kg"] = (
                    self.instance.capacite_dispo_kg + self.instance.capacite_reservee_kg
                )
                self.initial["capacite_totale_m3"] = (
                    self.instance.capacite_dispo_m3 + self.instance.capacite_reservee_m3
                )

    def clean_date_depart(self):
        date = self.cleaned_data["date_depart"]
        if date <= timezone.now():
            raise forms.ValidationError("La date de départ doit être dans le futur.")
        return date

    def clean_etapes(self):
        return [ville.strip() for ville in self.cleaned_data["etapes"].split(",") if ville.strip()]

    def clean(self):
        data = super().clean()
        depart, arrivee = data.get("ville_depart", "").strip(), data.get("ville_arrivee", "").strip()
        if depart and arrivee and depart.casefold() == arrivee.casefold():
            self.add_error("ville_arrivee", "La ville d’arrivée doit être différente de la ville de départ.")

        vehicule, poids, volume = data.get("vehicule"), data.get("capacite_totale_kg"), data.get("capacite_totale_m3")
        if poids is not None and poids <= 0:
            self.add_error("capacite_totale_kg", "La place proposée doit être supérieure à 0.")
        elif vehicule and poids and poids > vehicule.capacite_kg:
            self.add_error("capacite_totale_kg", f"Ce véhicule porte au plus {vehicule.capacite_kg} kg.")
        elif self.instance.pk and poids and poids < self.instance.capacite_reservee_kg:
            self.add_error("capacite_totale_kg", "Impossible de proposer moins que la place déjà réservée.")
        if volume is not None and volume <= 0:
            self.add_error("capacite_totale_m3", "La place proposée doit être supérieure à 0.")
        elif vehicule and volume and volume > vehicule.capacite_m3:
            self.add_error("capacite_totale_m3", f"Ce véhicule contient au plus {vehicule.capacite_m3} m³.")
        elif self.instance.pk and volume and volume < self.instance.capacite_reservee_m3:
            self.add_error("capacite_totale_m3", "Impossible de proposer moins que le volume déjà réservé.")
        return data

    def save(self, commit=True):
        trajet = super().save(commit=False)
        # Place libre = place proposée − ce qui est déjà réservé (rien pour un nouveau trajet).
        reserve_kg = trajet.capacite_reservee_kg if trajet.pk else Decimal("0")
        reserve_m3 = trajet.capacite_reservee_m3 if trajet.pk else Decimal("0")
        trajet.capacite_dispo_kg = trajet.capacite_totale_kg - reserve_kg
        trajet.capacite_dispo_m3 = trajet.capacite_totale_m3 - reserve_m3
        if commit:
            trajet.save()
            trajet.etapes.all().delete()
            EtapeTrajet.objects.bulk_create(
                EtapeTrajet(trajet=trajet, ville=ville, ordre=i)
                for i, ville in enumerate(self.cleaned_data["etapes"], 1)
            )
        return trajet


class PlanificationForm(forms.Form):
    """Mission prévisionnelle soumise au planificateur IA."""

    ville_depart = forms.CharField(label="Ville de départ", max_length=80)
    ville_arrivee = forms.CharField(label="Ville d’arrivée", max_length=80)
    date_depart = forms.DateField(
        label="Date prévue",
        initial=lambda: timezone.localdate() + timedelta(days=1),
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    poids_kg = forms.DecimalField(
        label="Poids à transporter (kg)", min_value=Decimal("0.01"), max_digits=10, decimal_places=2
    )
    volume_m3 = forms.DecimalField(
        label="Volume à transporter (m³)", min_value=Decimal("0.001"), max_digits=8, decimal_places=3
    )
    distance_km = forms.DecimalField(
        label="Distance estimée (km)", min_value=Decimal("1"), max_value=Decimal("5000"), max_digits=7, decimal_places=1
    )

    def clean_date_depart(self):
        date = self.cleaned_data["date_depart"]
        if date < timezone.localdate():
            raise forms.ValidationError("La date de départ doit être aujourd’hui ou plus tard.")
        return date

    def clean(self):
        data = super().clean()
        depart, arrivee = data.get("ville_depart", "").strip(), data.get("ville_arrivee", "").strip()
        if depart and arrivee and depart.casefold() == arrivee.casefold():
            self.add_error("ville_arrivee", "La ville d’arrivée doit être différente de la ville de départ.")
        return data
