from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm

from apps.core.roles import Role

from .models import ProfilPME, ProfilTransporteur, Utilisateur


class InscriptionForm(UserCreationForm):
    role = forms.ChoiceField(
        label="Je suis",
        choices=[(Role.PME, "Une PME qui veut expédier"), (Role.TRANSPORTEUR, "Un transporteur")],
        widget=forms.RadioSelect,
    )
    raison_sociale = forms.CharField(label="Nom de l’entreprise", required=False, help_text="Obligatoire pour une PME.")

    class Meta:
        model = Utilisateur
        fields = ("email", "first_name", "last_name", "telephone", "role")

    def clean(self):
        data = super().clean()
        if data.get("role") == Role.PME and not data.get("raison_sociale"):
            self.add_error("raison_sociale", "Indiquez le nom de votre entreprise.")
        return data

    def save(self, commit=True):
        user = super().save(commit=commit)
        if commit:
            if user.role == Role.PME:
                ProfilPME.objects.create(utilisateur=user, raison_sociale=self.cleaned_data["raison_sociale"])
            else:
                ProfilTransporteur.objects.create(utilisateur=user)
        return user


class ConnexionForm(AuthenticationForm):
    username = forms.EmailField(label="Email", widget=forms.EmailInput(attrs={"autofocus": True}))
