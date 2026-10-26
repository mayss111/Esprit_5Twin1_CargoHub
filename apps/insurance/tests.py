from datetime import timedelta

from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone

from apps.bookings.models import Notification, Reservation

from .forms import SinistreForm, TraitementSinistreForm
from .models import PieceJustificative, Sinistre


def donnees(expedition, **extra):
    values = {
        "expedition": expedition.pk,
        "titre": "Marchandise endommagée",
        "description": "Plusieurs cartons ont été endommagés pendant le transport.",
        "type_sinistre": Sinistre.Type.DOMMAGE,
        "date_incident": timezone.localdate().isoformat(),
        "montant_estime": "450.00",
    }
    values.update(extra)
    return values


def test_validation_sinistre(pme, expedition):
    form = SinistreForm(donnees(expedition, titre="", montant_estime="-1"), user=pme)
    assert not form.is_valid()
    assert "titre" in form.errors
    assert "montant_estime" in form.errors

    futur = timezone.localdate() + timedelta(days=1)
    form = SinistreForm(donnees(expedition, date_incident=futur.isoformat()), user=pme)
    assert not form.is_valid()
    assert "date_incident" in form.errors

    donnees_sans_expedition = donnees(expedition)
    donnees_sans_expedition["expedition"] = ""
    form = SinistreForm(donnees_sans_expedition, user=pme)
    assert not form.is_valid()
    assert "expedition" in form.errors


def test_expedition_d_un_autre_utilisateur_refusee(client, pme, autre_pme, expedition):
    autre = expedition.__class__.objects.create(
        pme=autre_pme,
        adresse_depart=expedition.adresse_depart,
        adresse_arrivee=expedition.adresse_arrivee,
        date_souhaitee=expedition.date_souhaitee,
        date_arrivee=expedition.date_arrivee,
    )
    client.force_login(pme)
    response = client.post(reverse("insurance:creer"), donnees(autre))
    assert response.status_code == 200
    assert not Sinistre.objects.exists()


def test_transporteur_voit_ses_sinistres(client, transporteur, expedition):
    sinistre = Sinistre.objects.create(
        auteur=transporteur,
        expedition=expedition,
        titre="Accident",
        description="Un incident est survenu pendant le transport de la marchandise.",
        type_sinistre=Sinistre.Type.ACCIDENT,
    )
    client.force_login(transporteur)
    assert sinistre.reference in client.get(reverse("insurance:liste")).content.decode()


def test_transporteur_peut_declarer_un_sinistre_sur_toute_expedition(client, transporteur, autre_pme, expedition):
    autre = expedition.__class__.objects.create(
        pme=autre_pme,
        adresse_depart=expedition.adresse_depart,
        adresse_arrivee=expedition.adresse_arrivee,
        date_souhaitee=expedition.date_souhaitee,
        date_arrivee=expedition.date_arrivee,
    )
    form = SinistreForm(donnees(autre), user=transporteur)
    assert form.is_valid(), form.errors
    client.force_login(transporteur)
    response = client.post(reverse("insurance:creer"), donnees(autre))
    assert response.status_code == 302
    assert Sinistre.objects.filter(auteur=transporteur, expedition=autre).exists()


def test_transporteur_voit_un_sinistre_de_son_transport(client, pme, transporteur, expedition, trajet):
    Reservation.objects.create(expedition=expedition, trajet=trajet)
    sinistre = Sinistre.objects.create(
        auteur=pme,
        expedition=expedition,
        titre="Perte partielle",
        description="Une partie de la marchandise manque à la réception.",
        type_sinistre=Sinistre.Type.PERTE_PARTIELLE,
    )
    client.force_login(transporteur)
    assert sinistre.reference in client.get(reverse("insurance:liste")).content.decode()
    assert client.get(reverse("insurance:detail", args=[sinistre.pk])).status_code == 200


def test_pme_voit_un_sinistre_de_son_expedition(client, pme, transporteur, expedition):
    sinistre = Sinistre.objects.create(
        auteur=transporteur,
        expedition=expedition,
        titre="Dossier transporteur",
        description="Le transporteur signale une perte sur cette expédition.",
        type_sinistre=Sinistre.Type.PERTE_PARTIELLE,
    )
    client.force_login(pme)
    assert sinistre.reference in client.get(reverse("insurance:liste")).content.decode()
    assert client.get(reverse("insurance:detail", args=[sinistre.pk])).status_code == 200


def test_montant_de_perte_reserve_a_la_pme(pme, transporteur, expedition):
    assert "montant_estime" in SinistreForm(user=pme).fields
    assert "montant_estime" not in SinistreForm(user=transporteur).fields


def test_justificatif_pdf_accepte(client, pme, expedition):
    client.force_login(pme)
    fichier = SimpleUploadedFile("preuve.pdf", b"%PDF-1.4", content_type="application/pdf")
    response = client.post(reverse("insurance:creer"), {**donnees(expedition), "justificatifs": [fichier]})
    assert response.status_code == 302
    sinistre = Sinistre.objects.get()
    assert PieceJustificative.objects.filter(sinistre=sinistre).count() == 1


def test_photo_justificative_s_affiche(client, pme, expedition):
    client.force_login(pme)
    fichier = SimpleUploadedFile("photo.jpg", b"fake-image", content_type="image/jpeg")
    response = client.post(reverse("insurance:creer"), {**donnees(expedition), "justificatifs": [fichier]})
    assert response.status_code == 302
    sinistre = Sinistre.objects.get()
    detail = client.get(reverse("insurance:detail", args=[sinistre.pk]))
    assert b"<img" in detail.content
    assert b"photo.jpg" in detail.content


def test_refus_admin_exige_une_justification(admin_user, pme, expedition):
    sinistre = Sinistre.objects.create(
        auteur=pme,
        expedition=expedition,
        titre="Perte totale",
        description="La marchandise est introuvable après le transport.",
        type_sinistre=Sinistre.Type.PERTE_TOTALE,
        statut=Sinistre.Statut.EN_COURS,
    )
    form = TraitementSinistreForm(
        {
            "statut": Sinistre.Statut.REFUSE,
            "assigne_a": admin_user.pk,
            "decision_admin": "",
            "justification_decision": "",
            "montant_rembourse": "",
        },
        instance=sinistre,
    )
    assert not form.is_valid()
    assert "justification_decision" in form.errors


def test_admin_accepte_un_sinistre(client, admin_user, pme, expedition):
    sinistre = Sinistre.objects.create(
        auteur=pme,
        expedition=expedition,
        titre="Marchandise endommagée",
        description="Les articles sont arrivés abîmés après le trajet.",
        type_sinistre=Sinistre.Type.DOMMAGE,
        statut=Sinistre.Statut.EN_COURS,
    )
    client.force_login(admin_user)
    response = client.post(
        reverse("bo_insurance:detail", args=[sinistre.pk]),
        {
            "statut": Sinistre.Statut.ACCEPTE,
            "assigne_a": admin_user.pk,
            "decision_admin": "Indemnisation acceptée.",
            "justification_decision": "Les preuves sont suffisantes.",
            "montant_rembourse": "300.00",
        },
    )
    assert response.status_code == 302
    sinistre.refresh_from_db()
    assert sinistre.statut == Sinistre.Statut.ACCEPTE
    assert sinistre.assigne_a == admin_user


def test_creation_sinistre_notifie_admin(client, pme, admin_user, expedition):
    client.force_login(pme)
    client.post(reverse("insurance:creer"), donnees(expedition))
    assert Notification.objects.filter(destinataire=admin_user, titre="Nouveau sinistre déclaré").exists()


def test_demande_documents_notifie_auteur(client, admin_user, pme, expedition):
    sinistre = Sinistre.objects.create(
        auteur=pme,
        expedition=expedition,
        titre="Perte totale",
        description="La marchandise est introuvable après le transport.",
        type_sinistre=Sinistre.Type.PERTE_TOTALE,
        statut=Sinistre.Statut.EN_COURS,
    )
    client.force_login(admin_user)
    response = client.post(
        reverse("bo_insurance:detail", args=[sinistre.pk]),
        {
            "statut": Sinistre.Statut.DOCUMENTS,
            "assigne_a": admin_user.pk,
            "decision_admin": "",
            "justification_decision": "",
            "montant_rembourse": "",
        },
    )
    assert response.status_code == 302
    sinistre.refresh_from_db()
    assert sinistre.statut == Sinistre.Statut.DOCUMENTS
    assert Notification.objects.filter(destinataire=pme, titre="Justificatifs complémentaires demandés").exists()


def test_modification_sinistre_notifie_admin(client, admin_user, pme, expedition):
    sinistre = Sinistre.objects.create(
        auteur=pme,
        expedition=expedition,
        titre="Perte initiale",
        description="La marchandise est introuvable après le transport.",
        type_sinistre=Sinistre.Type.PERTE_TOTALE,
    )
    client.force_login(pme)
    client.post(
        reverse("insurance:modifier", args=[sinistre.pk]),
        donnees(expedition, titre="Perte mise à jour"),
    )
    assert Notification.objects.filter(destinataire=admin_user, titre="Sinistre mis à jour").exists()


def test_date_incident_presente_dans_le_formulaire_de_modification(client, pme, expedition):
    sinistre = Sinistre.objects.create(
        auteur=pme,
        expedition=expedition,
        titre="Perte initiale",
        description="La marchandise est introuvable après le transport.",
        type_sinistre=Sinistre.Type.PERTE_TOTALE,
        date_incident=timezone.datetime(2026, 10, 16).date(),
    )
    client.force_login(pme)
    page = client.get(reverse("insurance:modifier", args=[sinistre.pk]))
    assert 'value="2026-10-16"' in page.content.decode()
