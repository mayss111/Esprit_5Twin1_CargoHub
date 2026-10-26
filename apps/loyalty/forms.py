from django import forms

from .models import CodePromo


class ParrainageForm(forms.Form):
    email = forms.EmailField(
        label="Email de votre parrain",
        widget=forms.EmailInput(attrs={"required": True, "autocomplete": "email"}),
    )


class CodePromoForm(forms.ModelForm):
    class Meta:
        model = CodePromo
        fields = ["code", "type", "valeur", "montant_minimum", "date_expiration", "usage_unique", "actif"]
        widgets = {
            "code": forms.TextInput(attrs={"required": True, "minlength": 3}),
            "valeur": forms.NumberInput(attrs={"min": "0.01", "step": "0.01", "required": True}),
            "montant_minimum": forms.NumberInput(attrs={"min": "0", "step": "0.01"}),
            "date_expiration": forms.DateInput(attrs={"type": "date"}),
        }

    def clean_code(self):
        code = self.cleaned_data["code"].strip().upper()
        if len(code) < 3:
            raise forms.ValidationError("Le code doit contenir au moins 3 caractères.")
        doublon = CodePromo.objects.filter(code__iexact=code)
        if self.instance.pk:
            doublon = doublon.exclude(pk=self.instance.pk)
        if doublon.exists():
            raise forms.ValidationError("Ce code existe déjà.")
        return code

    def clean_valeur(self):
        valeur = self.cleaned_data["valeur"]
        if valeur <= 0:
            raise forms.ValidationError("La valeur doit être supérieure à 0.")
        return valeur

    def clean(self):
        data = super().clean()
        if data.get("type") == CodePromo.Type.POURCENTAGE and data.get("valeur") and data["valeur"] > 100:
            self.add_error("valeur", "Le pourcentage ne peut pas dépasser 100.")
        return data
