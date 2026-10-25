from django import forms

from apps.accounts.models import Utilisateur
from apps.core.roles import Role

from .models import Reservation


class AnnulationLitigeForm(forms.Form):
    motif = forms.CharField(
        label="Motif de l’annulation",
        min_length=10,
        max_length=200,
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text="Obligatoire. Il est enregistré dans l’historique de la réservation.",
    )


class FiltreReservationsForm(forms.Form):
    """Filtres du back-office (formulaire GET : tous les champs sont facultatifs)."""

    q = forms.CharField(
        label="Rechercher",
        required=False,
        widget=forms.TextInput(attrs={"type": "search", "placeholder": "N°, référence, email…"}),
    )
    statut = forms.ChoiceField(label="Statut", required=False, choices=[("", "Tous")] + Reservation.Statut.choices)
    pme = forms.ModelChoiceField(label="PME", required=False, queryset=Utilisateur.objects.none(), empty_label="Toutes")
    transporteur = forms.ModelChoiceField(
        label="Transporteur", required=False, queryset=Utilisateur.objects.none(), empty_label="Tous"
    )
    du = forms.DateField(label="Du", required=False, widget=forms.DateInput(attrs={"type": "date"}))
    au = forms.DateField(label="Au", required=False, widget=forms.DateInput(attrs={"type": "date"}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["pme"].queryset = Utilisateur.objects.filter(role=Role.PME).order_by("email")
        self.fields["transporteur"].queryset = Utilisateur.objects.filter(role=Role.TRANSPORTEUR).order_by("email")

    def clean(self):
        data = super().clean()
        if data.get("du") and data.get("au") and data["du"] > data["au"]:
            self.add_error("au", "La date de fin doit être après la date de début.")
        return data
