"""Tests du module Messagerie & support (M1) : modération, assistant IA, conversations, tickets, back-office."""

from unittest import mock

import pytest
from asgiref.sync import async_to_sync
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.urls import reverse

from apps.accounts.models import Utilisateur
from apps.bookings.models import Reservation
from apps.core import ai
from apps.core.roles import Role
from apps.messaging.ai import REPONSE_PAR_DEFAUT, moderer, moderer_par_regles, repondre_support
from apps.messaging.models import Conversation, Message, TicketSupport
from apps.messaging.routing import websocket_urlpatterns
from apps.messaging.services import TEXTE_MASQUE, envoyer_message, texte_visible
from apps.messaging.tasks import repondre_ticket


@pytest.fixture
def reservation(expedition, trajet):
    return Reservation.objects.create(expedition=expedition, trajet=trajet, statut=Reservation.Statut.ACCEPTEE)


@pytest.fixture
def conversation(reservation, pme, transporteur):
    conv = Conversation.objects.create(reservation=reservation)
    conv.participants.add(pme, transporteur)
    return conv


@pytest.fixture
def intrus(db):
    return Utilisateur.objects.create_user("intrus@test.tn", "motdepasse123", role=Role.PME)


@pytest.fixture
def ticket(pme):
    return TicketSupport.objects.create(auteur=pme, sujet="Paiement refusé", description="Ma carte est refusée.")


# ---------------------------------------------------------------- IA : modération et assistant (tests unitaires)


@pytest.mark.parametrize(
    "texte, signale",
    [
        ("Appelle-moi au 98 123 456", True),
        ("Écris-moi : sami@gmail.com", True),
        ("On passe sur WhatsApp ?", True),
        ("Payez en espèces au chauffeur", True),
        ("Quel escroc !", True),
        ("Bonjour, le colis est prêt", False),
        ("Le suivi en direct ne marche pas", False),
        ("3 palettes de 450 kg", False),
    ],
)
def test_moderation_par_regles(texte, signale):
    assert moderer_par_regles(texte)["signale"] is signale


def test_moderation_utilise_le_llm_quand_disponible(settings):
    settings.AI_API_KEY = "cle-de-test"
    with mock.patch("apps.core.ai.demander", return_value='{"signale": true, "raison": "Menace"}'):
        assert moderer("Tu vas le regretter") == {"signale": True, "raison": "Menace"}
    with mock.patch("apps.core.ai.demander", return_value='{"signale": "false", "raison": "rien"}'):
        assert moderer("Bonjour") == {"signale": False, "raison": ""}


def test_moderation_repli_si_reponse_llm_illisible(settings):
    settings.AI_API_KEY = "cle-de-test"
    with mock.patch("apps.core.ai.demander", return_value="je ne sais pas"):
        assert moderer("Mon numéro 22 333 444")["signale"]


def test_assistant_faq_sans_cle():
    assert "Mot de passe oublié" in repondre_support("J'ai perdu mon mot de passe")
    assert repondre_support("Question sans rapport") == REPONSE_PAR_DEFAUT


def test_assistant_utilise_le_llm(settings):
    settings.AI_API_KEY = "cle-de-test"
    with mock.patch("apps.core.ai.demander", return_value="Réponse du modèle") as appel:
        assert repondre_support("Comment payer ?") == "Réponse du modèle"
    assert "CargoHub" in appel.call_args.kwargs["systeme"]


# ---------------------------------------------------------------- services et modèle


def test_envoyer_message_signale_et_masque(conversation, pme, transporteur):
    message = envoyer_message(conversation, pme, "Appelez-moi au 22 345 678")
    assert message.signale and message.raison_signalement == "Numéro de téléphone partagé"
    assert texte_visible(message, pme) == "Appelez-moi au 22 345 678"  # l'auteur voit son texte
    assert texte_visible(message, transporteur) == TEXTE_MASQUE


def test_envoyer_message_si_la_moderation_plante(conversation, pme):
    with mock.patch("apps.messaging.services.moderer", side_effect=RuntimeError("panne")):
        message = envoyer_message(conversation, pme, "Bonjour")
    assert message.pk and not message.signale


def test_interlocuteurs(conversation, pme, transporteur):
    assert conversation.interlocuteurs(pme) == [transporteur]
    assert str(conversation) == f"Conversation #{conversation.pk}"


def test_ticket_modifiable_seulement_ouvert(ticket):
    assert ticket.modifiable and str(ticket) == "Paiement refusé"
    ticket.statut = TicketSupport.Statut.EN_COURS
    assert not ticket.modifiable


def test_tache_repondre_ticket(ticket):
    repondre_ticket(ticket.pk)
    ticket.refresh_from_db()
    assert "paiement" in ticket.reponse_ia.lower()
    repondre_ticket(999_999)  # ticket supprimé entre-temps : aucune erreur


# ---------------------------------------------------------------- conversations (tests d'intégration)


def test_liste_des_conversations(client, conversation, pme, transporteur):
    Message.objects.create(conversation=conversation, auteur=transporteur, contenu="Bonjour")
    client.force_login(pme)
    reponse = client.get(reverse("messaging:liste"))
    assert reponse.status_code == 200
    assert reponse.context["object_list"][0].non_lus == 1
    assert "Karim" in reponse.content.decode()


def test_conversation_marque_les_messages_lus(client, conversation, pme, transporteur):
    message = Message.objects.create(conversation=conversation, auteur=transporteur, contenu="Bonjour Sami")
    client.force_login(pme)
    reponse = client.get(reverse("messaging:conversation", args=[conversation.pk]))
    assert reponse.status_code == 200 and "Bonjour Sami" in reponse.content.decode()
    message.refresh_from_db()
    assert message.lu


def test_conversation_d_un_autre_introuvable(client, conversation, intrus):
    client.force_login(intrus)
    assert client.get(reverse("messaging:conversation", args=[conversation.pk])).status_code == 404
    assert client.post(reverse("messaging:conversation", args=[conversation.pk]), {"contenu": "x"}).status_code == 404


def test_envoyer_un_message(client, conversation, pme):
    client.force_login(pme)
    reponse = client.post(reverse("messaging:conversation", args=[conversation.pk]), {"contenu": "Le colis est prêt"})
    assert reponse.status_code == 302
    assert conversation.messages.get().contenu == "Le colis est prêt"


def test_message_vide_refuse(client, conversation, pme):
    client.force_login(pme)
    reponse = client.post(reverse("messaging:conversation", args=[conversation.pk]), {"contenu": "   "})
    assert reponse.status_code == 200
    assert not conversation.messages.exists()


def test_message_signale_masque_pour_l_interlocuteur(client, conversation, pme, transporteur):
    client.force_login(pme)
    reponse = client.post(
        reverse("messaging:conversation", args=[conversation.pk]),
        {"contenu": "Payez-moi en liquide"},
        follow=True,
    )
    assert "signalé" in reponse.content.decode()
    client.force_login(transporteur)
    html = client.get(reverse("messaging:conversation", args=[conversation.pk])).content.decode()
    assert "Payez-moi en liquide" not in html and TEXTE_MASQUE in html


def test_nouvelle_conversation_depuis_une_reservation(client, reservation, pme, transporteur):
    client.force_login(transporteur)
    url = reverse("messaging:nouvelle")
    assert client.get(url, {"reservation": reservation.pk}).status_code == 200
    reponse = client.post(url, {"reservation": reservation.pk, "contenu": "Bonjour, je passe demain à 9h"})
    conversation = Conversation.objects.get(reservation=reservation)
    assert reponse.url == reverse("messaging:conversation", args=[conversation.pk])
    assert set(conversation.participants.all()) == {pme, transporteur}
    # Deuxième envoi : même conversation
    client.post(url, {"reservation": reservation.pk, "contenu": "Confirmé"})
    assert Conversation.objects.filter(reservation=reservation).count() == 1
    assert conversation.messages.count() == 2


def test_nouvelle_conversation_reservation_d_un_autre_refusee(client, reservation, intrus):
    client.force_login(intrus)
    reponse = client.post(reverse("messaging:nouvelle"), {"reservation": reservation.pk, "contenu": "Bonjour"})
    assert reponse.status_code == 200  # choix invalide
    assert not Conversation.objects.exists()


def test_supprimer_son_message(client, conversation, pme, transporteur):
    mien = Message.objects.create(conversation=conversation, auteur=pme, contenu="Erreur")
    sien = Message.objects.create(conversation=conversation, auteur=transporteur, contenu="Bonjour")
    client.force_login(pme)
    assert client.post(reverse("messaging:message_supprimer", args=[sien.pk])).status_code == 404
    client.post(reverse("messaging:message_supprimer", args=[mien.pk]))
    assert list(conversation.messages.all()) == [sien]


def test_chat_websocket(transactional_db, conversation, pme):
    application = URLRouter(websocket_urlpatterns)

    async def scenario():
        communicateur = WebsocketCommunicator(application, f"/ws/messagerie/{conversation.pk}/")
        communicateur.scope["user"] = pme
        connecte, _ = await communicateur.connect()
        assert connecte
        await communicateur.send_json_to({"message": "Mon numéro 22 345 678"})
        recu = await communicateur.receive_json_from()
        await communicateur.disconnect()
        return recu

    recu = async_to_sync(scenario)()
    assert recu["message"] == TEXTE_MASQUE and recu["auteur_id"] == pme.pk
    assert conversation.messages.get().signale


def test_chat_websocket_refuse_les_non_participants(transactional_db, conversation, intrus):
    async def scenario():
        communicateur = WebsocketCommunicator(URLRouter(websocket_urlpatterns), f"/ws/messagerie/{conversation.pk}/")
        communicateur.scope["user"] = intrus
        connecte, _ = await communicateur.connect()
        return connecte

    assert not async_to_sync(scenario)()


# ---------------------------------------------------------------- assistant et tickets


def test_assistant_repond(client, pme):
    client.force_login(pme)
    assert client.get(reverse("messaging:assistant")).status_code == 200
    reponse = client.post(reverse("messaging:assistant"), {"question": "Comment annuler une réservation ?"})
    html = reponse.content.decode()
    assert "annulée depuis sa page" in html
    assert reponse.context["duree_ms"] is not None
    assert 'data-ia="' in html  # spinner pendant l'appel IA


def test_assistant_en_panne(client, pme):
    client.force_login(pme)
    with mock.patch("apps.messaging.views.repondre_support", side_effect=ai.IAIndisponible("panne")):
        reponse = client.post(reverse("messaging:assistant"), {"question": "Comment payer ?"})
    assert reponse.status_code == 200
    assert "indisponible" in reponse.content.decode()


def test_assistant_question_trop_courte(client, pme):
    client.force_login(pme)
    reponse = client.post(reverse("messaging:assistant"), {"question": "?"})
    assert reponse.status_code == 200 and reponse.context["form"].errors


def test_creer_un_ticket_lance_la_reponse_ia(client, pme):
    client.force_login(pme)
    assert "annuler" in client.get(reverse("messaging:ticket_creer"), {"description": "annuler"}).content.decode()
    reponse = client.post(
        reverse("messaging:ticket_creer"),
        {"sujet": "Annulation", "description": "Je veux annuler ma réservation de demain", "priorite": "NORMALE"},
    )
    ticket = TicketSupport.objects.get()
    assert reponse.url == reverse("messaging:ticket", args=[ticket.pk])
    assert ticket.auteur == pme and ticket.reponse_ia  # Celery en mode immédiat dans les tests


def test_creer_un_ticket_meme_si_celery_est_indisponible(client, pme):
    client.force_login(pme)
    with mock.patch("apps.messaging.views.repondre_ticket.delay", side_effect=ConnectionError("Redis")):
        reponse = client.post(
            reverse("messaging:ticket_creer"),
            {"sujet": "Bug", "description": "La page de suivi reste blanche", "priorite": "HAUTE"},
        )
    assert reponse.status_code == 302 and TicketSupport.objects.count() == 1


def test_ticket_description_trop_courte(client, pme):
    client.force_login(pme)
    reponse = client.post(
        reverse("messaging:ticket_creer"), {"sujet": "x", "description": "court", "priorite": "BASSE"}
    )
    assert reponse.status_code == 200 and not TicketSupport.objects.exists()


def test_mes_tickets_seulement(client, ticket, intrus):
    TicketSupport.objects.create(auteur=intrus, sujet="Autre", description="Ticket de quelqu'un d'autre")
    client.force_login(ticket.auteur)
    reponse = client.get(reverse("messaging:tickets"))
    assert list(reponse.context["object_list"]) == [ticket]
    assert client.get(reverse("messaging:ticket", args=[ticket.pk])).status_code == 200
    client.force_login(intrus)
    for nom in ["ticket", "ticket_modifier", "ticket_supprimer"]:
        assert client.get(reverse(f"messaging:{nom}", args=[ticket.pk])).status_code == 404


def test_modifier_et_supprimer_un_ticket_ouvert(client, ticket):
    client.force_login(ticket.auteur)
    url = reverse("messaging:ticket_modifier", args=[ticket.pk])
    client.post(url, {"sujet": "Paiement", "description": "Ma carte est refusée depuis hier", "priorite": "HAUTE"})
    ticket.refresh_from_db()
    assert ticket.priorite == "HAUTE"
    client.post(reverse("messaging:ticket_supprimer", args=[ticket.pk]))
    assert not TicketSupport.objects.exists()


def test_ticket_pris_en_charge_non_modifiable(client, ticket):
    ticket.statut = TicketSupport.Statut.EN_COURS
    ticket.save()
    client.force_login(ticket.auteur)
    assert client.get(reverse("messaging:ticket_modifier", args=[ticket.pk])).status_code == 404
    assert client.post(reverse("messaging:ticket_supprimer", args=[ticket.pk])).status_code == 404


# ---------------------------------------------------------------- back-office


def test_backoffice_tickets_filtre(client, admin_user, ticket):
    client.force_login(admin_user)
    url = reverse("bo_messaging:liste")
    assert ticket in client.get(url, {"statut": "OUVERT"}).context["object_list"]
    assert ticket not in client.get(url, {"statut": "RESOLU"}).context["object_list"]


def test_backoffice_traiter_un_ticket(client, admin_user, ticket):
    ticket.reponse_ia = "Vérifiez le plafond de votre carte."
    ticket.save()
    client.force_login(admin_user)
    url = reverse("bo_messaging:ticket", args=[ticket.pk])
    reponse = client.get(url)
    assert reponse.context["form"].initial["reponse_admin"] == ticket.reponse_ia  # suggestion IA pré-remplie

    # Résolu sans réponse : refusé
    reponse = client.post(url, {"statut": "RESOLU", "priorite": "NORMALE", "reponse_admin": ""})
    assert reponse.status_code == 200 and reponse.context["form"].errors

    client.post(url, {"statut": "RESOLU", "priorite": "NORMALE", "reponse_admin": "Carte débloquée."})
    ticket.refresh_from_db()
    assert ticket.statut == "RESOLU" and ticket.assigne_a == admin_user
    client.force_login(ticket.auteur)
    assert "Carte débloquée." in client.get(reverse("messaging:ticket", args=[ticket.pk])).content.decode()


def test_backoffice_supprimer_un_ticket(client, admin_user, ticket):
    client.force_login(admin_user)
    assert client.get(reverse("bo_messaging:ticket_supprimer", args=[ticket.pk])).status_code == 200
    client.post(reverse("bo_messaging:ticket_supprimer", args=[ticket.pk]))
    assert not TicketSupport.objects.exists()


def test_backoffice_moderation(client, admin_user, conversation, pme):
    signale = envoyer_message(conversation, pme, "Écris-moi sur WhatsApp")
    a_supprimer = envoyer_message(conversation, pme, "Espèce d'escroc")
    client.force_login(admin_user)
    url = reverse("bo_messaging:moderation")
    assert set(client.get(url).context["object_list"]) == {signale, a_supprimer}

    client.post(reverse("bo_messaging:moderer", args=[signale.pk]), {"action": "retablir"})
    signale.refresh_from_db()
    assert not signale.signale
    client.post(reverse("bo_messaging:moderer", args=[a_supprimer.pk]), {"action": "inconnue"})
    assert Message.objects.filter(pk=a_supprimer.pk).exists()
    client.post(reverse("bo_messaging:moderer", args=[a_supprimer.pk]), {"action": "supprimer"})
    assert not Message.objects.filter(pk=a_supprimer.pk).exists()


@pytest.mark.parametrize("nom, args", [("liste", []), ("moderation", []), ("ticket", [1]), ("ticket_supprimer", [1])])
def test_backoffice_messagerie_interdit_aux_pme(client, pme, nom, args):
    client.force_login(pme)
    assert client.get(reverse(f"bo_messaging:{nom}", args=args)).status_code == 403
