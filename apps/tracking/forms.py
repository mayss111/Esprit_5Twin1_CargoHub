from django import forms

from .models import Avis, Incident


class PositionForm(forms.Form):
    latitude = forms.FloatField(
        label="Latitude",
        min_value=-90,
        max_value=90,
        help_text="Obligatoire. Nombre entre -90 et 90. Exemple : 36.8",
        widget=forms.NumberInput(
            attrs={"min": -90, "max": 90, "step": "any", "required": True, "title": "Latitude entre -90 et 90"}
        ),
    )
    longitude = forms.FloatField(
        label="Longitude",
        min_value=-180,
        max_value=180,
        help_text="Obligatoire. Nombre entre -180 et 180. Exemple : 10.18",
        widget=forms.NumberInput(
            attrs={"min": -180, "max": 180, "step": "any", "required": True, "title": "Longitude entre -180 et 180"}
        ),
    )


class PreuveForm(forms.Form):
    photo = forms.ImageField(
        label="Photo de la livraison",
        required=False,
        help_text="Facultative. Fichier image uniquement (JPG ou PNG).",
        widget=forms.ClearableFileInput(attrs={"accept": "image/*"}),
    )


class ConfirmationForm(forms.Form):
    code = forms.CharField(
        label="Code remis par le transporteur",
        min_length=6,
        max_length=6,
        help_text="Obligatoire. Exactement 6 chiffres, sans espace.",
        widget=forms.TextInput(
            attrs={
                "inputmode": "numeric",
                "pattern": "[0-9]{6}",
                "minlength": 6,
                "maxlength": 6,
                "autocomplete": "one-time-code",
                "required": True,
                "title": "6 chiffres",
            }
        ),
    )

    def clean_code(self):
        code = self.cleaned_data["code"].strip()
        if not code.isdigit() or len(code) != 6:
            raise forms.ValidationError("Le code doit contenir exactement 6 chiffres.")
        return code


class IncidentForm(forms.ModelForm):
    class Meta:
        model = Incident
        fields = ["type", "description"]
        help_texts = {"description": "Obligatoire. Au moins 10 caractères."}
        widgets = {
            "description": forms.Textarea(
                attrs={"rows": 3, "minlength": 10, "required": True, "title": "Au moins 10 caractères"}
            )
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        description = self.fields["description"]
        description.widget.attrs["minlength"] = 10
        type_incident = self.fields["type"]
        type_incident.choices = [("", "Choisissez un type")] + [
            (valeur, libelle) for valeur, libelle in type_incident.choices if valeur
        ]
        type_incident.widget.attrs.update({"required": True, "title": "Choisissez un type d'incident."})
        type_incident.error_messages["required"] = "Choisissez un type d'incident."

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
        help_texts = {
            "note": "Obligatoire. Nombre entier de 1 à 5.",
            "commentaire": "Facultatif. Si le texte contredit la note, le texte l’emporte.",
        }
        widgets = {
            "note": forms.NumberInput(
                attrs={"min": 1, "max": 5, "step": 1, "required": True, "title": "Note de 1 à 5"}
            ),
            "commentaire": forms.Textarea(attrs={"rows": 3, "maxlength": 1000}),
        }

    def clean_note(self):
        note = self.cleaned_data["note"]
        if not 1 <= note <= 5:
            raise forms.ValidationError("La note doit être comprise entre 1 et 5.")
        return note
