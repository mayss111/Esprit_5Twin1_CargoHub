from django import forms
from django.core.validators import FileExtensionValidator
from django.db.models import Q
from django.utils import timezone

from apps.accounts.forms import EXTENSIONS_DOCUMENTS, valider_document
from apps.accounts.models import Utilisateur
from apps.core.roles import Role, est_admin
from apps.shipments.models import Expedition

from .models import PieceJustificative, Sinistre


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    widget = MultipleFileInput

    def clean(self, data, initial=None):
        single_clean = super().clean
        if isinstance(data, (list, tuple)):
            return [single_clean(item, initial) for item in data]
        return [single_clean(data, initial)] if data else []


class SinistreForm(forms.ModelForm):
    justificatifs = MultipleFileField(
        label="Justificatifs",
        required=False,
        validators=[FileExtensionValidator(EXTENSIONS_DOCUMENTS), valider_document],
        widget=MultipleFileInput(attrs={"class": "form-control", "accept": ".pdf,.jpg,.jpeg,.png", "multiple": True}),
        help_text="Photos JPG/PNG ou PDF, 5 Mo maximum par fichier.",
    )

    class Meta:
        model = Sinistre
        fields = (
            "expedition",
            "partie_mise_en_cause",
            "titre",
            "description",
            "type_sinistre",
            "date_incident",
            "montant_estime",
            "justificatifs",
        )
        labels = {
            "expedition": "Expédition concernée",
            "partie_mise_en_cause": "Sinistre contre",
            "titre": "Titre",
            "description": "Description détaillée",
            "type_sinistre": "Type de sinistre",
            "date_incident": "Date de l'incident",
            "montant_estime": "Montant estimé (DT)",
        }
        widgets = {
            "expedition": forms.Select(attrs={"class": "form-select"}),
            "partie_mise_en_cause": forms.Select(attrs={"class": "form-select"}),
            "titre": forms.TextInput(attrs={"class": "form-control", "minlength": 5, "maxlength": 150}),
            "description": forms.Textarea(
                attrs={"class": "form-control", "rows": 6, "minlength": 20, "maxlength": 5000}
            ),
            "type_sinistre": forms.Select(attrs={"class": "form-select"}),
            "date_incident": forms.DateInput(format="%Y-%m-%d", attrs={"class": "form-control", "type": "date"}),
            "montant_estime": forms.NumberInput(attrs={"class": "form-control", "min": "0", "step": "0.01"}),
        }

    def __init__(self, *args, user, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
        if est_admin(user):
            queryset = Expedition.objects.all()
        elif user.role == Role.PME:
            queryset = Expedition.objects.filter(pme=user)
        else:
            # Un transporteur peut déclarer un sinistre dès qu'il identifie
            # l'expédition concernée, même si aucune réservation n'est encore
            # enregistrée à son nom.
            queryset = Expedition.objects.all()
        self.fields["expedition"].queryset = queryset.select_related(
            "pme", "adresse_depart", "adresse_arrivee"
        ).order_by("-created_at")
        self.fields["expedition"].required = True
        self.fields["date_incident"].input_formats = ["%Y-%m-%d"]
        self.fields["expedition"].label_from_instance = lambda expedition: (
            f"{expedition.reference} — PME : {expedition.pme} — "
            f"{expedition.adresse_depart.ville} → {expedition.adresse_arrivee.ville}"
        )
        if user.role != Role.PME:
            self.fields.pop("montant_estime", None)
        else:
            self.fields["montant_estime"].label = "Montant estimé de la perte (DT)"
            self.fields["montant_estime"].help_text = "Montant de la perte estimé par la PME."
        cible_role = Role.TRANSPORTEUR if user.role == Role.PME else Role.PME
        self.fields["partie_mise_en_cause"].queryset = Utilisateur.objects.filter(
            role=cible_role, is_active=True
        ).order_by("email")
        self.fields["partie_mise_en_cause"].required = False
        self.fields["partie_mise_en_cause"].help_text = (
            "Sélectionnez le transporteur concerné."
            if user.role == Role.PME
            else "Sélectionnez l'expéditeur concerné."
        )

    def clean_titre(self):
        titre = self.cleaned_data.get("titre", "").strip()
        if len(titre) < 5:
            raise forms.ValidationError("Le titre doit contenir au moins 5 caractères utiles.")
        return titre

    def clean_description(self):
        description = " ".join(self.cleaned_data.get("description", "").strip().split())
        if len(description) < 20:
            raise forms.ValidationError("Décrivez le sinistre en au moins 20 caractères utiles.")
        return description

    def clean_date_incident(self):
        date_incident = self.cleaned_data["date_incident"]
        if date_incident > timezone.localdate():
            raise forms.ValidationError("La date de l'incident ne peut pas être dans le futur.")
        return date_incident

    def clean_expedition(self):
        expedition = self.cleaned_data.get("expedition")
        if expedition is None:
            # Le champ obligatoire a déjà ajouté son erreur ; ne jamais
            # accéder à pk sur une valeur absente ou invalide.
            return expedition
        if not self.fields["expedition"].queryset.filter(pk=expedition.pk).exists():
            raise forms.ValidationError("Cette expédition ne vous est pas accessible.")
        return expedition

    def clean(self):
        data = super().clean()
        cible = data.get("partie_mise_en_cause")
        if cible:
            role_attendu = Role.TRANSPORTEUR if self.user.role == Role.PME else Role.PME
            if cible.role != role_attendu:
                self.add_error("partie_mise_en_cause", "Sélectionnez une partie correspondant à votre rôle.")
        return data


class TraitementSinistreForm(forms.ModelForm):
    class Meta:
        model = Sinistre
        fields = ("statut", "assigne_a", "decision_admin", "justification_decision", "montant_rembourse")
        labels = {
            "statut": "Statut",
            "assigne_a": "Administrateur responsable",
            "decision_admin": "Décision administrative",
            "justification_decision": "Justification",
            "montant_rembourse": "Montant remboursé (DT)",
        }
        widgets = {
            "statut": forms.Select(attrs={"class": "form-select"}),
            "assigne_a": forms.Select(attrs={"class": "form-select"}),
            "decision_admin": forms.Textarea(attrs={"class": "form-control", "rows": 5}),
            "justification_decision": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "montant_rembourse": forms.NumberInput(attrs={"class": "form-control", "min": "0", "step": "0.01"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["assigne_a"].queryset = Utilisateur.objects.filter(
            Q(is_superuser=True) | Q(role=Role.ADMIN), is_active=True
        )

    def clean(self):
        data = super().clean()
        statut = data.get("statut")
        if statut and self.instance.pk and not self.instance.peut_passer_a(statut):
            self.add_error("statut", "Cette transition de statut n'est pas autorisée.")
        if statut == Sinistre.Statut.REFUSE and not data.get("justification_decision", "").strip():
            self.add_error("justification_decision", "Une justification est obligatoire pour refuser un sinistre.")
        if statut == Sinistre.Statut.ACCEPTE and not data.get("decision_admin", "").strip():
            self.add_error("decision_admin", "Écrivez la décision avant d'accepter le sinistre.")
        return data


class PieceJustificativeForm(forms.ModelForm):
    class Meta:
        model = PieceJustificative
        fields = ("fichier",)

    def clean_fichier(self):
        fichier = self.cleaned_data["fichier"]
        FileExtensionValidator(EXTENSIONS_DOCUMENTS)(fichier)
        return valider_document(fichier)
