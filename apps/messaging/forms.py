from django import forms
from django.core.validators import FileExtensionValidator
from django.db.models import Q

from apps.accounts.forms import EXTENSIONS_DOCUMENTS, valider_document
from apps.accounts.models import Utilisateur
from apps.bookings.models import Reservation
from apps.core.roles import Role

from .models import Message, TicketSupport

# FileExtensionValidator attend les extensions sans point.
EXTENSIONS_AUDIO = ("webm", "ogg", "mp3", "wav", "m4a", "mp4", "mpeg", "mpga")
TAILLE_MAX_AUDIO = 25 * 1024 * 1024


def valider_audio(fichier):
    if fichier and getattr(fichier, "size", 0) > TAILLE_MAX_AUDIO:
        raise forms.ValidationError("Le vocal dépasse 25 Mo.")
    return fichier


class MessageForm(forms.ModelForm):
    class Meta:
        model = Message
        fields = ("contenu", "piece_jointe", "fichier_audio")
        labels = {
            "contenu": "Votre message",
            "piece_jointe": "Pièce jointe (facultatif)",
            "fichier_audio": "Message vocal (facultatif)",
        }
        widgets = {"contenu": forms.Textarea(attrs={"rows": 2, "maxlength": 2000})}
        help_texts = {
            "contenu": "Facultatif si vous envoyez une pièce jointe.",
            "piece_jointe": "PDF, JPG ou PNG, 5 Mo maximum.",
            "fichier_audio": "WebM, OGG, MP3, WAV ou M4A, 25 Mo maximum.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["contenu"].required = False
        self.fields["piece_jointe"].validators += [FileExtensionValidator(EXTENSIONS_DOCUMENTS), valider_document]
        self.fields["piece_jointe"].widget.attrs["accept"] = ".pdf,.jpg,.jpeg,.png"
        self.fields["fichier_audio"].required = False
        self.fields["fichier_audio"].validators += [FileExtensionValidator(EXTENSIONS_AUDIO), valider_audio]
        self.fields["fichier_audio"].widget.attrs.update(
            {"accept": "audio/*", "capture": "user", "data-audio-input": ""}
        )

    def clean_contenu(self):
        return self.cleaned_data.get("contenu", "").strip()

    def clean(self):
        data = super().clean()
        if not data.get("contenu") and not data.get("piece_jointe") and not data.get("fichier_audio"):
            self.add_error("contenu", "Ajoutez un texte, une pièce jointe ou un message vocal.")
        return data


class NouvelleConversationForm(forms.Form):
    interlocuteur = forms.ModelChoiceField(
        label="Utilisateur à contacter",
        queryset=Utilisateur.objects.none(),
        required=False,
        empty_label="Choisissez une PME ou un transporteur",
    )
    reservation = forms.ModelChoiceField(
        label="Réservation concernée (facultatif)",
        queryset=Reservation.objects.none(),
        required=False,
        empty_label="Aucune réservation",
    )
    contenu = forms.CharField(label="Premier message", widget=forms.Textarea(attrs={"rows": 3}), max_length=2000)

    def __init__(self, *args, user, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
        if user.role == Role.PME:
            interlocuteurs = Utilisateur.objects.filter(role=Role.TRANSPORTEUR, is_active=True)
        elif user.role == Role.TRANSPORTEUR:
            interlocuteurs = Utilisateur.objects.filter(role=Role.PME, is_active=True)
        else:
            interlocuteurs = Utilisateur.objects.filter(role__in=[Role.PME, Role.TRANSPORTEUR], is_active=True)
        self.fields["interlocuteur"].queryset = interlocuteurs.exclude(pk=user.pk).order_by("email")
        self.fields["reservation"].queryset = reservations_de(user).select_related(
            "expedition__adresse_depart", "expedition__adresse_arrivee"
        )

    def clean(self):
        data = super().clean()
        interlocuteur = data.get("interlocuteur")
        reservation = data.get("reservation")
        if not reservation and not interlocuteur:
            self.add_error("interlocuteur", "Choisissez un utilisateur pour démarrer la conversation.")
        if reservation and interlocuteur:
            parties = {reservation.expedition.pme_id, reservation.trajet.transporteur_id}
            if interlocuteur.pk not in parties:
                self.add_error("interlocuteur", "Cet utilisateur ne participe pas à la réservation choisie.")
        return data


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
