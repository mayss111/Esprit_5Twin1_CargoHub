from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator, RegexValidator

from apps.core.roles import Role

from .models import ProfilPME, ProfilTransporteur, Utilisateur

TELEPHONE_TN = RegexValidator(r"^(\+216\s?)?\d{2}\s?\d{3}\s?\d{3}$", "Numéro tunisien à 8 chiffres, ex. 22 123 456.")
EXTENSIONS_DOCUMENTS = ["pdf", "jpg", "jpeg", "png"]
TAILLE_MAX_DOCUMENT = 5 * 1024 * 1024  # 5 Mo


def valider_document(fichier):
    """Permis, carte grise, lettre de voiture… : PDF ou image, 5 Mo maximum."""
    if fichier and getattr(fichier, "size", 0) > TAILLE_MAX_DOCUMENT:
        raise ValidationError("Le fichier dépasse 5 Mo.")
    return fichier


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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["email"].label = "Adresse email"
        self.fields["first_name"].label = "Prénom"
        self.fields["last_name"].label = "Nom"
        self.fields["telephone"].label = "Téléphone"
        self.fields["password1"].label = "Mot de passe"
        self.fields["password2"].label = "Confirmation du mot de passe"
        self.fields["telephone"].validators.append(TELEPHONE_TN)

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
    username = forms.EmailField(label="Adresse email", widget=forms.EmailInput(attrs={"autofocus": True}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["password"].label = "Mot de passe"


# ---------------------------------------------------------------- profil, documents, back-office


class ProfilUtilisateurForm(forms.ModelForm):
    class Meta:
        model = Utilisateur
        fields = ("first_name", "last_name", "telephone")
        labels = {"first_name": "Prénom", "last_name": "Nom", "telephone": "Téléphone"}
        widgets = {"telephone": forms.TextInput(attrs={"inputmode": "tel", "autocomplete": "tel"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["first_name"].required = True
        self.fields["last_name"].required = True
        self.fields["telephone"].validators.append(TELEPHONE_TN)


class ProfilPMEForm(forms.ModelForm):
    class Meta:
        model = ProfilPME
        fields = ("raison_sociale", "matricule_fiscal", "secteur", "adresse", "ville")
        labels = {
            "raison_sociale": "Nom de l’entreprise",
            "matricule_fiscal": "Matricule fiscal",
            "secteur": "Secteur d’activité",
        }
        help_texts = {"matricule_fiscal": "Format : 1234567A/B/M/000"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["matricule_fiscal"].validators.append(
            RegexValidator(r"^\d{7}[A-Z](/[A-Z]/[A-Z]/\d{3})?$", "Format attendu : 1234567A/B/M/000.")
        )


class ProfilTransporteurForm(forms.ModelForm):
    class Meta:
        model = ProfilTransporteur
        fields = ("numero_permis", "permis", "carte_grise")
        labels = {"numero_permis": "Numéro de permis", "permis": "Permis de conduire", "carte_grise": "Carte grise"}
        help_texts = {"permis": "PDF, JPG ou PNG, 5 Mo maximum.", "carte_grise": "PDF, JPG ou PNG, 5 Mo maximum."}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for champ in ("permis", "carte_grise"):
            self.fields[champ].validators += [FileExtensionValidator(EXTENSIONS_DOCUMENTS), valider_document]
            self.fields[champ].widget.attrs["accept"] = ".pdf,.jpg,.jpeg,.png"

    def save(self, commit=True):
        profil = super().save(commit=False)
        # Un nouveau document doit être revérifié par un administrateur.
        if {"permis", "carte_grise"} & set(self.changed_data):
            profil.statut_validation = ProfilTransporteur.Statut.EN_ATTENTE
        if commit:
            profil.save()
        return profil


class BackofficeUtilisateurForm(forms.ModelForm):
    class Meta:
        model = Utilisateur
        fields = ("first_name", "last_name", "telephone", "role", "is_active")
        labels = {
            "first_name": "Prénom",
            "last_name": "Nom",
            "telephone": "Téléphone",
            "role": "Rôle",
            "is_active": "Compte actif",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["telephone"].validators.append(TELEPHONE_TN)


class ValidationTransporteurForm(forms.ModelForm):
    class Meta:
        model = ProfilTransporteur
        fields = ("statut_validation",)
        labels = {"statut_validation": "Décision"}
