from django import forms
from django.db.models import Q

from apps.accounts.models import Utilisateur
from apps.core.roles import Role, est_admin
from apps.shipments.models import Expedition

from .models import Reclamation


class ReclamationForm(forms.ModelForm):
    class Meta:
        model = Reclamation
        fields = ("expedition", "partie_mise_en_cause", "titre", "description", "type_reclamation")
        labels = {
            "expedition": "Expédition concernée",
            "partie_mise_en_cause": "Réclamation contre",
            "titre": "Titre",
            "description": "Description détaillée",
            "type_reclamation": "Type de réclamation",
        }
        widgets = {
            "expedition": forms.Select(attrs={"class": "form-select"}),
            "partie_mise_en_cause": forms.Select(attrs={"class": "form-select"}),
            "titre": forms.TextInput(attrs={"class": "form-control", "minlength": 5, "maxlength": 150}),
            "description": forms.Textarea(
                attrs={"class": "form-control", "rows": 6, "minlength": 20, "maxlength": 5000}
            ),
            "type_reclamation": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, user, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
        if est_admin(user):
            queryset = Expedition.objects.all()
        elif user.role == Role.PME:
            queryset = Expedition.objects.filter(pme=user)
        else:
            # Un transporteur peut signaler un problème sur n'importe quelle
            # expédition, y compris avant la création d'une réservation.
            queryset = Expedition.objects.all()
        self.fields["expedition"].queryset = queryset.select_related(
            "pme", "adresse_depart", "adresse_arrivee"
        ).order_by("-created_at")
        self.fields["expedition"].label_from_instance = lambda expedition: (
            f"{expedition.reference} — PME : {expedition.pme} — "
            f"{expedition.adresse_depart.ville} → {expedition.adresse_arrivee.ville}"
        )
        self.fields["titre"].help_text = "Entre 5 et 150 caractères."
        self.fields["description"].help_text = "Décrivez le problème en au moins 20 caractères."
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
            raise forms.ValidationError("Décrivez le problème en au moins 20 caractères utiles.")
        return description

    def clean_expedition(self):
        expedition = self.cleaned_data["expedition"]
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


class TraitementReclamationForm(forms.ModelForm):
    class Meta:
        model = Reclamation
        fields = ("statut", "assigne_a", "reponse_admin", "justification_decision")
        labels = {
            "statut": "Statut",
            "assigne_a": "Administrateur responsable",
            "reponse_admin": "Réponse administrative",
            "justification_decision": "Justification de la décision",
        }
        widgets = {
            "statut": forms.Select(attrs={"class": "form-select"}),
            "assigne_a": forms.Select(attrs={"class": "form-select"}),
            "reponse_admin": forms.Textarea(attrs={"class": "form-control", "rows": 5}),
            "justification_decision": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["assigne_a"].queryset = Utilisateur.objects.filter(
            Q(is_superuser=True) | Q(role=Role.ADMIN), is_active=True
        ).order_by("email")

    def clean(self):
        data = super().clean()
        statut = data.get("statut")
        if statut and self.instance.pk and not self.instance.peut_passer_a(statut):
            self.add_error("statut", "Cette transition de statut n'est pas autorisée.")
        if statut == Reclamation.Statut.REJETEE and not data.get("justification_decision", "").strip():
            self.add_error("justification_decision", "Une justification est obligatoire pour rejeter une réclamation.")
        if statut == Reclamation.Statut.RESOLUE and not data.get("reponse_admin", "").strip():
            self.add_error("reponse_admin", "Écrivez une réponse avant de résoudre la réclamation.")
        return data
