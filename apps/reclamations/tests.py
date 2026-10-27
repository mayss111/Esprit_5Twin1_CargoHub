from django.urls import reverse

from apps.bookings.models import Notification, Reservation

from .forms import ReclamationForm, TraitementReclamationForm
from .models import Reclamation


def donnees(expedition, **extra):
    valeurs = {
        "expedition": expedition.pk,
        "titre": "Retard de livraison",
        "description": "La livraison est arrivée avec deux jours de retard.",
        "type_reclamation": Reclamation.Type.RETARD,
    }
    valeurs.update(extra)
    return valeurs


def test_creation_et_validation_des_champs(pme, expedition):
    form = ReclamationForm(donnees(expedition, titre="  ", description="   "), user=pme)
    assert not form.is_valid()
    assert "titre" in form.errors and "description" in form.errors

    form = ReclamationForm(donnees(expedition, type_reclamation="INVENTE"), user=pme)
    assert not form.is_valid()
    assert "type_reclamation" in form.errors


def test_pme_ne_peut_pas_selectionner_l_expedition_d_un_autre(client, pme, autre_pme, expedition):
    autre_expedition = expedition.__class__.objects.create(
        pme=autre_pme,
        adresse_depart=expedition.adresse_depart,
        adresse_arrivee=expedition.adresse_arrivee,
        date_souhaitee=expedition.date_souhaitee,
        date_arrivee=expedition.date_arrivee,
    )
    client.force_login(pme)
    response = client.post(reverse("reclamations:creer"), donnees(autre_expedition))
    assert response.status_code == 200
    assert not Reclamation.objects.exists()


def test_un_utilisateur_ne_voit_que_ses_reclamations(client, pme, autre_pme, expedition):
    autre_expedition = expedition.__class__.objects.create(
        pme=autre_pme,
        adresse_depart=expedition.adresse_depart,
        adresse_arrivee=expedition.adresse_arrivee,
        date_souhaitee=expedition.date_souhaitee,
        date_arrivee=expedition.date_arrivee,
    )
    reclamation = Reclamation.objects.create(
        auteur=autre_pme,
        expedition=autre_expedition,
        titre="Un dossier privé",
        description="Cette réclamation appartient à une autre personne.",
        type_reclamation=Reclamation.Type.AUTRE,
    )
    client.force_login(pme)
    assert reclamation.reference not in client.get(reverse("reclamations:liste")).content.decode()
    assert client.get(reverse("reclamations:detail", args=[reclamation.pk])).status_code == 404


def test_pme_voit_une_reclamation_de_son_expedition(client, pme, transporteur, expedition):
    reclamation = Reclamation.objects.create(
        auteur=transporteur,
        expedition=expedition,
        titre="Dossier transporteur",
        description="Le transporteur signale un problème sur cette expédition.",
        type_reclamation=Reclamation.Type.AUTRE,
    )
    client.force_login(pme)
    assert reclamation.reference in client.get(reverse("reclamations:liste")).content.decode()
    assert client.get(reverse("reclamations:detail", args=[reclamation.pk])).status_code == 200


def test_transporteur_voit_une_reclamation_de_son_transport(client, pme, transporteur, expedition, trajet):
    Reservation.objects.create(expedition=expedition, trajet=trajet)
    reclamation = Reclamation.objects.create(
        auteur=pme,
        expedition=expedition,
        titre="Marchandise endommagée",
        description="La marchandise est arrivée endommagée après le transport.",
        type_reclamation=Reclamation.Type.AUTRE,
    )
    client.force_login(transporteur)
    assert reclamation.reference in client.get(reverse("reclamations:liste")).content.decode()
    assert client.get(reverse("reclamations:detail", args=[reclamation.pk])).status_code == 200


def test_transporteur_peut_creer_une_reclamation_sur_toute_expedition(client, transporteur, autre_pme, expedition):
    autre_expedition = expedition.__class__.objects.create(
        pme=autre_pme,
        adresse_depart=expedition.adresse_depart,
        adresse_arrivee=expedition.adresse_arrivee,
        date_souhaitee=expedition.date_souhaitee,
        date_arrivee=expedition.date_arrivee,
    )
    form = ReclamationForm(donnees(autre_expedition), user=transporteur)
    assert form.is_valid(), form.errors
    client.force_login(transporteur)
    response = client.post(reverse("reclamations:creer"), donnees(autre_expedition))
    assert response.status_code == 302
    assert Reclamation.objects.filter(auteur=transporteur, expedition=autre_expedition).exists()


def test_rejet_exige_une_justification(admin_user, pme, expedition):
    reclamation = Reclamation.objects.create(
        auteur=pme,
        expedition=expedition,
        titre="Problème de paiement",
        description="Le montant annoncé ne correspond pas au montant facturé.",
        type_reclamation=Reclamation.Type.PAIEMENT,
        statut=Reclamation.Statut.EN_COURS,
    )
    form = TraitementReclamationForm(
        {
            "statut": Reclamation.Statut.REJETEE,
            "assigne_a": admin_user.pk,
            "reponse_admin": "",
            "justification_decision": "",
        },
        instance=reclamation,
    )
    assert not form.is_valid()
    assert "justification_decision" in form.errors


def test_admin_traite_une_reclamation(client, admin_user, pme, expedition):
    reclamation = Reclamation.objects.create(
        auteur=pme,
        expedition=expedition,
        titre="Retard important",
        description="La livraison présente un retard important et documenté.",
        type_reclamation=Reclamation.Type.RETARD,
        statut=Reclamation.Statut.EN_ATTENTE,
    )
    client.force_login(admin_user)
    response = client.post(
        reverse("bo_reclamations:detail", args=[reclamation.pk]),
        {
            "statut": Reclamation.Statut.EN_COURS,
            "assigne_a": admin_user.pk,
            "reponse_admin": "Nous analysons le dossier.",
            "justification_decision": "",
        },
    )
    assert response.status_code == 302
    reclamation.refresh_from_db()
    assert reclamation.statut == Reclamation.Statut.EN_COURS
    assert reclamation.assigne_a == admin_user


def test_creation_reclamation_notifie_admin(client, pme, admin_user, expedition):
    client.force_login(pme)
    client.post(reverse("reclamations:creer"), donnees(expedition))
    assert Notification.objects.filter(destinataire=admin_user, titre="Nouvelle réclamation").exists()


def test_decision_reclamation_notifie_auteur(client, admin_user, pme, expedition):
    reclamation = Reclamation.objects.create(
        auteur=pme,
        expedition=expedition,
        titre="Retard important",
        description="La livraison présente un retard important et documenté.",
        type_reclamation=Reclamation.Type.RETARD,
        statut=Reclamation.Statut.EN_COURS,
    )
    client.force_login(admin_user)
    response = client.post(
        reverse("bo_reclamations:detail", args=[reclamation.pk]),
        {
            "statut": Reclamation.Statut.RESOLUE,
            "assigne_a": admin_user.pk,
            "reponse_admin": "Dossier traité.",
            "justification_decision": "Analyse terminée.",
        },
    )
    assert response.status_code == 302
    reclamation.refresh_from_db()
    assert reclamation.statut == Reclamation.Statut.RESOLUE
    assert Notification.objects.filter(destinataire=pme, titre="Décision concernant votre réclamation").exists()


def test_modification_reclamation_notifie_admin(client, admin_user, pme, expedition):
    reclamation = Reclamation.objects.create(
        auteur=pme,
        expedition=expedition,
        titre="Retard initial",
        description="La livraison présente un retard important et documenté.",
        type_reclamation=Reclamation.Type.RETARD,
    )
    client.force_login(pme)
    client.post(
        reverse("reclamations:modifier", args=[reclamation.pk]),
        donnees(expedition, titre="Retard modifié"),
    )
    assert Notification.objects.filter(destinataire=admin_user, titre="Réclamation mise à jour").exists()
