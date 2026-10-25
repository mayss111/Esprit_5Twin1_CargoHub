"""Vérification IA des marchandises : Gemini est simulé, les règles CargoHub décident."""

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from apps.bookings.models import Notification
from apps.bookings.services import ReservationImpossible, reserver
from apps.shipments.forms import SaisieExpedition
from apps.shipments.models import Expedition, RegleInterdite
from apps.shipments.services.ai_checker import (
    ArticleIA,
    VerificationIndisponible,
    _parser,
    appliquer_verification,
    conclure,
    metriques_interdiction,
)
from apps.shipments.tests import _article, _donnees

pytestmark = pytest.mark.django_db


def _publier(pme, description="Textile emballé pour le transport", **article):
    jour = timezone.localdate() + timedelta(days=4)
    donnees = _donnees(jour, [_article(description=description, **article)])
    return SaisieExpedition(donnees, pme=pme, publier=True).save()


def test_articles_autorises_publies(pme):
    expedition = _publier(pme)
    assert expedition.statut == Expedition.Statut.PUBLIEE
    assert expedition.controles_recents.get().decision == "AUTORISE"


def test_un_article_interdit_refuse_et_notifie(pme):
    expedition = _publier(pme, description="Une caisse d'explosifs pour le chantier")
    assert expedition.statut == Expedition.Statut.REFUSEE
    assert "explosifs" in expedition.motif_decision.lower() or "Explosifs" in expedition.motif_decision
    assert Notification.objects.filter(destinataire=pme, titre="Expédition refusée").count() == 1
    appliquer_verification(expedition)
    assert Notification.objects.filter(destinataire=pme, titre="Expédition refusée").count() == 1


def test_plusieurs_articles_un_interdit_refuse_tout(pme):
    jour = timezone.localdate() + timedelta(days=4)
    articles = [
        _article(description="Textile emballé pour le transport"),
        _article(designation="Caisse spéciale", description="Une caisse d'explosifs de chantier"),
    ]
    expedition = SaisieExpedition(_donnees(jour, articles), pme=pme, publier=True).save()
    assert expedition.statut == Expedition.Statut.REFUSEE
    assert expedition.articles.count() == 2


@override_settings(GEMINI_API_KEY="cle-test")
def test_description_suspecte_sans_regle_part_en_verification(pme):
    def faux(articles, regles):
        return [
            ArticleIA(
                identifiant=article.pk,
                nom=article.designation,
                categorie_declaree=article.type_marchandise,
                categorie_proposee="Produit dangereux",
                risque="ELEVE",
                suspicion=True,
                verification_manuelle=True,
                motif="La description est trop vague pour écarter un risque.",
            )
            for article in articles
        ], 18

    with patch("apps.shipments.services.ai_checker.appeler_gemini", side_effect=faux):
        expedition = _publier(pme, description="Produit chimique non précisé pour l'atelier")
    assert expedition.statut == Expedition.Statut.A_VERIFIER
    assert expedition.duree_verification_ms == 18
    assert expedition.statut != Expedition.Statut.PUBLIEE


@override_settings(GEMINI_API_KEY="cle-test")
def test_api_indisponible_laisse_le_brouillon(pme):
    with patch(
        "apps.shipments.services.ai_checker.appeler_gemini",
        side_effect=VerificationIndisponible("indisponible"),
    ):
        expedition = _publier(pme)
    assert expedition.statut == Expedition.Statut.BROUILLON
    assert "indisponible" in expedition.motif_decision.lower() or "pas été publiée" in expedition.motif_decision


def test_reponse_json_incorrecte():
    article = SimpleNamespace(pk=1)
    with pytest.raises(VerificationIndisponible):
        _parser("ce n'est pas du json", [article])


def test_correction_puis_nouvelle_soumission(pme):
    expedition = _publier(pme, description="Une caisse d'explosifs pour le chantier")
    assert expedition.statut == Expedition.Statut.REFUSEE
    article = expedition.articles.get()
    jour = expedition.date_souhaitee
    nouvelles = _donnees(
        jour,
        [_article(id=article.pk, description="Textile emballé pour le transport")],
        initial=1,
    )
    corrige = SaisieExpedition(nouvelles, expedition=expedition, publier=True).save()
    assert corrige.statut == Expedition.Statut.PUBLIEE
    assert corrige.controles.count() == 2


def test_refus_bloque_le_matching(pme, trajet):
    expedition = _publier(pme, description="Une caisse d'explosifs pour le chantier")
    with pytest.raises(ReservationImpossible):
        reserver(expedition, trajet)


def test_pme_ne_consulte_pas_les_verifications_admin(client, pme):
    client.force_login(pme)
    assert client.get(reverse("bo_shipments:verifications")).status_code == 403
    assert client.get(reverse("bo_shipments:interdictions")).status_code == 403


def _en_verification(pme):
    def faux(articles, regles):
        return [
            ArticleIA(
                identifiant=article.pk,
                nom=article.designation,
                categorie_declaree=article.type_marchandise,
                risque="MOYEN",
                suspicion=True,
                verification_manuelle=True,
                motif="Description ambiguë.",
            )
            for article in articles
        ], 5

    with (
        override_settings(GEMINI_API_KEY="cle-test"),
        patch("apps.shipments.services.ai_checker.appeler_gemini", side_effect=faux),
    ):
        return _publier(pme, description="Produit non identifié à contrôler avant le départ")


def test_admin_accepte_et_notifie_la_pme(client, admin_user, pme):
    expedition = _en_verification(pme)
    client.force_login(admin_user)
    page = client.get(reverse("bo_shipments:verifications"))
    assert b"Accepter" in page.content
    assert b"Refuser" in page.content
    reponse = client.post(
        reverse("bo_shipments:verification_decision", args=[expedition.pk]),
        {"decision": "accepter"},
    )
    assert reponse.status_code == 302
    expedition.refresh_from_db()
    assert expedition.statut == Expedition.Statut.PUBLIEE
    assert expedition.controles_recents.get().decision == "AUTORISE"
    notification = Notification.objects.get(destinataire=pme, titre="Expédition acceptée")
    client.force_login(pme)
    accueil = client.get(reverse("shipments:liste"))
    assert "Expédition acceptée" in accueil.content.decode()
    ouverture = client.get(reverse("shipments:notification", args=[notification.pk]))
    assert ouverture.status_code == 302
    assert ouverture.url == reverse("shipments:detail", args=[expedition.pk])
    notification.refresh_from_db()
    assert notification.lu is True


def test_admin_refuse_avec_motif_et_notifie(client, admin_user, pme):
    expedition = _en_verification(pme)
    client.force_login(admin_user)
    sans_motif = client.post(
        reverse("bo_shipments:verification_decision", args=[expedition.pk]), {"decision": "refuser"}
    )
    assert sans_motif.status_code == 302
    expedition.refresh_from_db()
    assert expedition.statut == Expedition.Statut.A_VERIFIER
    motif = "Le contenu réel de l'article n'est pas établi."
    client.post(
        reverse("bo_shipments:verification_decision", args=[expedition.pk]),
        {"decision": "refuser", "motif": motif},
    )
    expedition.refresh_from_db()
    assert expedition.statut == Expedition.Statut.REFUSEE
    assert expedition.motif_decision == motif
    assert Notification.objects.filter(destinataire=pme, titre="Expédition refusée", message__contains=motif).exists()


def test_pme_ne_decide_pas_une_verification(client, pme):
    expedition = _en_verification(pme)
    client.force_login(pme)
    assert (
        client.post(
            reverse("bo_shipments:verification_decision", args=[expedition.pk]),
            {"decision": "accepter"},
        ).status_code
        == 403
    )
    expedition.refresh_from_db()
    assert expedition.statut == Expedition.Statut.A_VERIFIER


def test_admin_filtre_les_verifications(client, admin_user, pme):
    refusee = _publier(pme, description="Une caisse d'explosifs pour le chantier")
    en_attente = _en_verification(pme)
    client.force_login(admin_user)
    page = client.get(reverse("bo_shipments:verifications")).content.decode()
    assert "data-filtre-auto" in page
    assert "shipments/js/filtre.js" in page
    assert ">Filtrer<" not in page
    assert 'name="email"' in page
    assert ">Entreprise<" not in page
    par_email = client.get(reverse("bo_shipments:verifications"), {"email": pme.email}).content.decode()
    assert refusee.reference in par_email
    assert en_attente.reference in par_email
    inconnu = client.get(reverse("bo_shipments:verifications"), {"email": "absent@exemple.tn"}).content.decode()
    assert "ne correspond" in inconnu
    assert refusee.reference in page
    assert en_attente.reference in page
    seulement = client.get(reverse("bo_shipments:verifications"), {"statut": "REFUSEE", "q": refusee.reference})
    html = seulement.content.decode()
    assert refusee.reference in html
    assert en_attente.reference not in html
    autre = client.get(reverse("bo_shipments:verifications"), {"statut": "PUBLIEE"}).content.decode()
    assert "ne correspond" in autre
    assert refusee.reference not in autre
    expedition = _publier(pme, description="Une caisse d'explosifs pour le chantier")
    client.force_login(admin_user)
    page = client.get(reverse("bo_shipments:verifications"))
    assert page.status_code == 200
    assert expedition.reference in page.content.decode()
    regle = RegleInterdite.objects.get(nom="Explosifs")
    reponse = client.post(
        reverse("bo_shipments:interdiction_modifier", args=[regle.pk]),
        {
            "nom": regle.nom,
            "description": regle.description,
            "motif": regle.motif,
            "mots_cles": regle.mots_cles,
        },
    )
    assert reponse.status_code == 302
    regle.refresh_from_db()
    assert regle.actif is False


def test_admin_filtre_les_interdictions(client, admin_user):
    client.force_login(admin_user)
    page = client.get(reverse("bo_shipments:interdictions")).content.decode()
    assert "data-filtre-auto" in page
    assert "shipments/js/filtre.js" in page
    assert ">Filtrer<" not in page
    assert "Explosifs" in page
    assert "Armes" in page
    par_nom = client.get(reverse("bo_shipments:interdictions"), {"q": "explos"}).content.decode()
    assert "Explosifs" in par_nom
    assert "Armes" not in par_nom
    RegleInterdite.objects.filter(nom="Armes").update(actif=False)
    inactives = client.get(reverse("bo_shipments:interdictions"), {"actif": "0"}).content.decode()
    assert "Armes" in inactives
    assert "Explosifs" not in inactives
    vide = client.get(reverse("bo_shipments:interdictions"), {"q": "introuvable"}).content.decode()
    assert "ne correspond" in vide


def test_metriques_du_jeu_etiquete():
    regles = list(RegleInterdite.objects.all())
    exemples = [
        ("Cartons de vêtements", "Textile emballé pour le transport", "TEXTILE", None, Expedition.Statut.PUBLIEE),
        ("Caisse", "Une caisse d'explosifs de chantier", "GENERAL", None, Expedition.Statut.REFUSEE),
        ("Bidons", "Bouteilles de gaz inflammable", "GENERAL", None, Expedition.Statut.REFUSEE),
        ("Pièces", "Pièces détachées diverses non identifiées", "GENERAL", "ELEVE", Expedition.Statut.A_VERIFIER),
    ]
    predits = []
    for index, (nom, description, categorie, risque, _attendu) in enumerate(exemples, start=1):
        article = SimpleNamespace(pk=index, designation=nom, description=description, type_marchandise=categorie)
        avis = []
        if risque:
            avis = [
                ArticleIA(
                    identifiant=index,
                    nom=nom,
                    categorie_declaree=categorie,
                    risque=risque,
                    suspicion=True,
                    verification_manuelle=True,
                    motif="À confirmer",
                )
            ]
        statut, _lignes = conclure([article], regles, avis)
        predits.append(statut)
    mesures = metriques_interdiction([item[4] for item in exemples], predits)
    assert mesures["precision"] == 1
    assert mesures["rappel"] == 1
    assert mesures["f1"] == 1
    assert mesures["matrice"][Expedition.Statut.REFUSEE][Expedition.Statut.REFUSEE] == 2
