from django import forms


class CodePromoSaisiForm(forms.Form):
    code = forms.CharField(
        label="Code promo",
        min_length=3,
        max_length=30,
        help_text="Obligatoire. 3 à 30 caractères, lettres ou chiffres.",
        widget=forms.TextInput(
            attrs={
                "required": True,
                "autocomplete": "off",
                "minlength": 3,
                "maxlength": 30,
                "pattern": "[A-Za-z0-9]{3,30}",
                "title": "3 à 30 lettres ou chiffres",
            }
        ),
    )

    def clean_code(self):
        code = self.cleaned_data["code"].strip().upper()
        if len(code) < 3 or not code.isalnum():
            raise forms.ValidationError("Le code doit contenir 3 à 30 lettres ou chiffres.")
        return code
