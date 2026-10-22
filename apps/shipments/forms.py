"""Formulaires de saisie d'une expédition et de ses articles."""

from decimal import Decimal

from django import forms
from django.core.validators import MinValueValidator
from django.db import transaction
from django.forms import inlineformset_factory
from django.utils import timezone

from .models import CATEGORIES_INTERDITES, Adresse, ArticleExpedie, Expedition

GOUVERNORATS = [
    ("Ariana", "Ariana"),
    ("Béja", "Béja"),
    ("Ben Arous", "Ben Arous"),
    ("Bizerte", "Bizerte"),
    ("Gabès", "Gabès"),
    ("Gafsa", "Gafsa"),
    ("Jendouba", "Jendouba"),
    ("Kairouan", "Kairouan"),
    ("Kasserine", "Kasserine"),
    ("Kébili", "Kébili"),
    ("Le Kef", "Le Kef"),
    ("Mahdia", "Mahdia"),
    ("La Manouba", "La Manouba"),
    ("Médenine", "Médenine"),
    ("Monastir", "Monastir"),
    ("Nabeul", "Nabeul"),
    ("Sfax", "Sfax"),
    ("Sidi Bouzid", "Sidi Bouzid"),
    ("Siliana", "Siliana"),
    ("Sousse", "Sousse"),
    ("Tataouine", "Tataouine"),
    ("Tozeur", "Tozeur"),
    ("Tunis", "Tunis"),
    ("Zaghouan", "Zaghouan"),
]


def _exiger_minimum(champ, minimum, message):
    champ.validators = [v for v in champ.validators if not isinstance(v, MinValueValidator)]
    champ.validators.append(MinValueValidator(minimum, message))


class AdresseForm(forms.ModelForm):
    gouvernorat = forms.ChoiceField(label="Gouvernorat", choices=GOUVERNORATS)

    class Meta:
        model = Adresse
        fields = ("ligne", "ville", "gouvernorat", "code_postal")
        widgets = {
            "ligne": forms.TextInput(attrs={"class": "form-control form-control-sm"}),
            "ville": forms.TextInput(attrs={"class": "form-control form-control-sm"}),
            "code_postal": forms.TextInput(attrs={"class": "form-control form-control-sm"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["gouvernorat"].widget.attrs["class"] = "form-select form-select-sm"
        self.fields["ligne"].label = "Rue"
        self.fields["ville"].label = "Ville"
        self.fields["code_postal"].label = "Code postal"
        self.fields["code_postal"].required = False


class ExpeditionForm(forms.ModelForm):
    """Informations générales. Le statut est décidé au moment de l'enregistrement."""

    date_souhaitee = forms.DateField(
        label="Date d'expédition",
        input_formats=["%Y-%m-%d"],
        widget=forms.DateInput(
            format="%Y-%m-%d",
            attrs={"type": "date", "class": "form-control form-control-sm"},
        ),
    )

    class Meta:
        model = Expedition
        fields = ("date_souhaitee", "description")
        widgets = {
            "description": forms.Textarea(attrs={"rows": 1, "class": "form-control form-control-sm"}),
        }
        labels = {"description": "Description"}

    def __init__(self, *args, publier=False, **kwargs):
        self.publier = publier
        super().__init__(*args, **kwargs)

    def clean_date_souhaitee(self):
        date = self.cleaned_data["date_souhaitee"]
        creation = self.instance.pk is None
        if (creation or self.publier) and date < timezone.localdate():
            raise forms.ValidationError("La date d'expédition ne peut pas être dans le passé.")
        return date


class ArticleExpedieForm(forms.ModelForm):
    class Meta:
        model = ArticleExpedie
        fields = (
            "designation",
            "description",
            "type_marchandise",
            "quantite",
            "poids_kg",
            "volume_m3",
            "fragile",
            "valeur_declaree",
        )
        widgets = {
            "designation": forms.TextInput(attrs={"class": "form-control form-control-sm"}),
            "description": forms.TextInput(attrs={"class": "form-control form-control-sm"}),
            "type_marchandise": forms.Select(attrs={"class": "form-select form-select-sm"}),
            "quantite": forms.NumberInput(attrs={"class": "form-control form-control-sm", "min": 1}),
            "poids_kg": forms.NumberInput(
                attrs={"class": "form-control form-control-sm", "min": "0.01", "step": "0.01"}
            ),
            "volume_m3": forms.NumberInput(
                attrs={"class": "form-control form-control-sm", "min": "0.001", "step": "0.001"}
            ),
            "valeur_declaree": forms.NumberInput(
                attrs={"class": "form-control form-control-sm", "min": "0", "step": "0.01"}
            ),
        }
        labels = {
            "designation": "Nom de l'article",
            "type_marchandise": "Catégorie",
            "quantite": "Quantité",
            "poids_kg": "Poids (kg)",
            "volume_m3": "Volume (m³)",
            "fragile": "Fragile",
            "valeur_declaree": "Valeur déclarée (DT)",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["description"].required = False
        self.fields["valeur_declaree"].required = False
        _exiger_minimum(self.fields["quantite"], 1, "La quantité doit être supérieure à zéro.")
        _exiger_minimum(self.fields["poids_kg"], Decimal("0.01"), "Le poids doit être supérieur à zéro.")
        _exiger_minimum(self.fields["volume_m3"], Decimal("0.001"), "Le volume doit être supérieur à zéro.")


ArticleFormSet = inlineformset_factory(
    Expedition,
    ArticleExpedie,
    form=ArticleExpedieForm,
    extra=1,
    can_delete=True,
    min_num=0,
    max_num=30,
    validate_max=True,
)


def articles_retenus(formset):
    """Articles réellement saisis, sans les lignes vides ni celles cochées pour suppression."""
    retenus = []
    for form in formset.forms:
        data = getattr(form, "cleaned_data", None)
        if not data or data.get("DELETE"):
            continue
        if not data.get("designation"):
            continue
        retenus.append(data)
    return retenus


def controler_publication(articles):
    """Règles supplémentaires appliquées seulement au moment de publier."""
    erreurs = []
    if not articles:
        erreurs.append("Ajoutez au moins un article pour publier l'expédition.")
    for article in articles:
        if article.get("type_marchandise") in CATEGORIES_INTERDITES:
            nom = article.get("designation") or "cet article"
            erreurs.append(f"La catégorie de « {nom} » est interdite au transport.")
    if erreurs:
        raise forms.ValidationError(erreurs)


class SaisieExpedition:
    """Regroupe l'expédition, les deux adresses et le formset d'articles."""

    def __init__(self, data=None, *, expedition=None, pme=None, publier=False):
        self.publier = publier
        self.expedition = expedition
        self.pme = expedition.pme if expedition is not None else pme
        self.depart = AdresseForm(
            data,
            prefix="depart",
            instance=None if expedition is None else expedition.adresse_depart,
        )
        self.arrivee = AdresseForm(
            data,
            prefix="arrivee",
            instance=None if expedition is None else expedition.adresse_arrivee,
        )
        self.generale = ExpeditionForm(data, prefix="generale", instance=expedition, publier=publier)
        instance = expedition if expedition is not None else Expedition(pme=self.pme)
        self.articles = ArticleFormSet(data, prefix="articles", instance=instance)

    def is_valid(self):
        formulaires_valides = all(
            [
                self.depart.is_valid(),
                self.arrivee.is_valid(),
                self.generale.is_valid(),
                self.articles.is_valid(),
            ]
        )
        if self.expedition is not None and self.expedition.pk and not self.expedition.peut_etre_modifiee():
            self.generale.add_error(None, "Cette expédition ne peut plus être modifiée.")
            return False
        if not formulaires_valides:
            return False
        if self.publier or (self.expedition is not None and self.expedition.statut == Expedition.Statut.PUBLIEE):
            try:
                controler_publication(articles_retenus(self.articles))
            except forms.ValidationError as exc:
                self.generale.add_error(None, exc)
                return False
        return True

    def save(self):
        if not self.is_valid():
            raise ValueError("Le formulaire d'expédition est invalide.")
        with transaction.atomic():
            expedition = self.generale.save(commit=False)
            expedition.pme = self.pme
            expedition.adresse_depart = self.depart.save()
            expedition.adresse_arrivee = self.arrivee.save()
            if self.publier:
                expedition.statut = Expedition.Statut.PUBLIEE
            elif expedition.pk is None or expedition.statut == Expedition.Statut.BROUILLON:
                expedition.statut = Expedition.Statut.BROUILLON
            expedition.save()
            self.articles.instance = expedition
            self.articles.save()
        return expedition
