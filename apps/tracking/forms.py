from django import forms

from .models import Avis, Incident


class PositionForm(forms.Form):
    latitude = forms.FloatField(
        label="Latitude",
        min_value=-90,
        max_value=90,
        widget=forms.NumberInput(attrs={"min": -90, "max": 90, "step": "any", "required": True}),
    )
    longitude = forms.FloatField(
        label="Longitude",
        min_value=-180,
        max_value=180,
        widget=forms.NumberInput(attrs={"min": -180, "max": 180, "step": "any", "required": True}),
    )


class PreuveForm(forms.Form):
    photo = forms.ImageField(
        label="Photo de la livraison",
        required=False,
        widget=forms.ClearableFileInput(attrs={"accept": "image/*"}),
    )


class ConfirmationForm(forms.Form):
    code = forms.CharField(
        label="Code remis par le transporteur",
        min_length=6,
        max_length=6,
        widget=forms.TextInput(
            attrs={
                "inputmode": "numeric",
                "pattern": "[0-9]{6}",
                "minlength": 6,
                "maxlength": 6,
                "autocomplete": "one-time-code",
                "required": True,
            }
        ),
    )


class IncidentForm(forms.ModelForm):
    class Meta:
        model = Incident
        fields = ["type", "description"]
        widgets = {"description": forms.Textarea(attrs={"rows": 3, "minlength": 10, "required": True})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["description"].widget.attrs["minlength"] = 10

    def clean_description(self):
        texte = self.cleaned_data["description"].strip()
        if len(texte) < 10:
            raise forms.ValidationError("Décrivez l’incident en au moins 10 caractères.")
        return texte


class IncidentAdminForm(IncidentForm):
    class Meta(IncidentForm.Meta):
        fields = ["type", "description", "statut"]


class AvisForm(forms.ModelForm):
    class Meta:
        model = Avis
        fields = ["note", "commentaire"]
        widgets = {
            "note": forms.NumberInput(attrs={"min": 1, "max": 5, "required": True}),
            "commentaire": forms.Textarea(attrs={"rows": 3}),
        }

    def clean_note(self):
        note = self.cleaned_data["note"]
        if not 1 <= note <= 5:
            raise forms.ValidationError("La note doit être comprise entre 1 et 5.")
        return note
