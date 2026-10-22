from django import forms
from django.core.validators import FileExtensionValidator

from apps.accounts.forms import EXTENSIONS_DOCUMENTS, valider_document

from .models import DocumentTransport


class DocumentTransportForm(forms.ModelForm):
    class Meta:
        model = DocumentTransport
        fields = ("type", "fichier")
        labels = {"type": "Type de document", "fichier": "Fichier"}
        help_texts = {"fichier": "PDF, JPG ou PNG, 5 Mo maximum."}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["fichier"].validators += [FileExtensionValidator(EXTENSIONS_DOCUMENTS), valider_document]
        self.fields["fichier"].widget.attrs["accept"] = ".pdf,.jpg,.jpeg,.png"
