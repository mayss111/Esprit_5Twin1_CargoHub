from django import forms
from django.core.validators import FileExtensionValidator
from django.db.models import Q

from apps.accounts.forms import EXTENSIONS_DOCUMENTS, valider_document
from apps.accounts.models import Utilisateur
from apps.bookings.models import Reservation
from apps.core.roles import Role

from .models import Message, TicketSupport


class MessageForm(forms.ModelForm):
    class Meta:
        model = Message
        fields = ("contenu", "piece_jointe")
        labels = {"contenu": "Votre message", "piece_jointe": "Pièce jointe (facultatif)"}
        widgets = {"contenu": forms.Textarea(attrs={"rows": 2, "maxlength": 2000})}
        help_texts = {"piece_jointe": "PDF, JPG ou PNG, 5 Mo maximum."}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["piece_jointe"].validators += [FileExtensionValidator(EXTENSIONS_DOCUMENTS), valider_document]
        self.fields["piece_jointe"].widget.attrs["accept"] = ".pdf,.jpg,.jpeg,.png"

    def clean_contenu(self):
        contenu = self.cleaned_data["contenu"].strip()
        if not contenu:
            raise forms.ValidationError("Le message est vide.")
        return contenu


class NouvelleConversationForm(forms.Form):
    reservation = forms.ModelChoiceField(
        label="Réservation concernée", queryset=Reservation.objects.none(), empty_label="Choisissez une réservation"
    )
    contenu = forms.CharField(label="Premier message", widget=forms.Textarea(attrs={"rows": 3}), max_length=2000)

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["reservation"].queryset = reservations_de(user).select_related(
            "expedition__adresse_depart", "expedition__adresse_arrivee"
        )


def reservations_de(user):
    """Réservations où l'utilisateur est la PME ou le transporteur."""
    return Reservation.objects.filter(Q(expedition__pme=user) | Q(trajet__transporteur=user))


class QuestionSupportForm(forms.Form):
    question = forms.CharField(
        label="Votre question",
        min_length=5,
        max_length=500,
        widget=forms.Textarea(attrs={"rows": 3, "placeholder": "Ex. : comment annuler une réservation ?"}),
    )


class TicketForm(forms.ModelForm):
    class Meta:
        model = TicketSupport
        fields = ("sujet", "description", "priorite")
        labels = {"sujet": "Sujet", "description": "Décrivez votre problème", "priorite": "Priorité"}
        widgets = {"description": forms.Textarea(attrs={"rows": 5})}

    def clean_description(self):
        description = self.cleaned_data["description"].strip()
        if len(description) < 10:
            raise forms.ValidationError("Décrivez le problème en au moins 10 caractères.")
        return description


class TraitementTicketForm(forms.ModelForm):
    """Back-office : l'admin prend en charge, répond et clôture."""

    class Meta:
        model = TicketSupport
        fields = ("statut", "priorite", "assigne_a", "reponse_admin")
        labels = {
            "statut": "Statut",
            "priorite": "Priorité",
            "assigne_a": "Assigné à",
            "reponse_admin": "Réponse à l’utilisateur",
        }
        widgets = {"reponse_admin": forms.Textarea(attrs={"rows": 4})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["assigne_a"].queryset = Utilisateur.objects.filter(
            Q(is_superuser=True) | Q(role=Role.ADMIN), is_active=True
        )

    def clean(self):
        data = super().clean()
        if data.get("statut") == TicketSupport.Statut.RESOLU and not data.get("reponse_admin", "").strip():
            self.add_error("reponse_admin", "Écrivez une réponse avant de marquer le ticket comme résolu.")
        return data
