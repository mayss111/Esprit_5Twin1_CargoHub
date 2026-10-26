from django import forms


class CodePromoSaisiForm(forms.Form):
    code = forms.CharField(
        label="Code promo",
        max_length=30,
        widget=forms.TextInput(attrs={"required": True, "autocomplete": "off", "minlength": 2}),
    )

    def clean_code(self):
        return self.cleaned_data["code"].strip()
