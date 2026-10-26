from django import forms

from .models import CodePromo


class ParrainageForm(forms.Form):
    email = forms.EmailField(
        label="Email de votre parrain",
        help_text="Obligatoire. Adresse email d’un compte CargoHub. Vous ne pouvez pas vous parrainer vous-même.",
        widget=forms.EmailInput(
            attrs={"required": True, "autocomplete": "email", "maxlength": 254, "title": "Adresse email valide"}
        ),
    )


class CodePromoForm(forms.ModelForm):
    class Meta:
        model = CodePromo
        fields = ["code", "type", "valeur", "montant_minimum", "date_expiration", "usage_unique", "actif"]
        help_texts = {
            "code": "Obligatoire. Au moins 3 caractères. Il est enregistré en majuscules.",
            "valeur": "Obligatoire, supérieure à 0. Pour un pourcentage, 100 maximum.",
            "montant_minimum": "0 ou plus. Le code ne s’applique pas en dessous de ce montant.",
            "date_expiration": "Facultative. Un code expiré est refusé au paiement.",
        }
        widgets = {
            "code": forms.TextInput(
                attrs={"required": True, "minlength": 3, "maxlength": 30, "title": "Au moins 3 caractères"}
            ),
            "valeur": forms.NumberInput(
                attrs={"min": "0.01", "step": "0.01", "required": True, "title": "Supérieure à 0"}
            ),
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
