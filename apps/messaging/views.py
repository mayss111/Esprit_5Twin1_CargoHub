"""Vues du module Messagerie & support — Membre 1.

Front-office : conversations liées à une réservation, assistant de support (IA), tickets.
Back-office  : traitement des tickets et modération des messages signalés par l'IA.
"""

import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.contrib import messages
from django.db.models import Count, Max, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, DeleteView, DetailView, FormView, UpdateView

from apps.core import ai
from apps.core.mixins import AdminRequiredMixin, RoleRequiredMixin
from apps.core.views import ListeBackofficeView, ListeFrontView

from .ai import REPONSE_PAR_DEFAUT, repondre_support
from .forms import MessageForm, NouvelleConversationForm, QuestionSupportForm, TicketForm, TraitementTicketForm
from .models import Conversation, Message, TicketSupport
from .services import ConversationBloquee, TEXTE_MASQUE, envoyer_message, texte_visible
from .tasks import repondre_ticket

logger = logging.getLogger(__name__)


def diffuser(message):
    """Prévient en direct les autres participants (WebSocket). Sans serveur de canaux, la page se recharge."""
    try:
        async_to_sync(get_channel_layer().group_send)(
            f"conversation_{message.conversation_id}",
            {
                "type": "chat.message",
                "message": TEXTE_MASQUE if message.signale else message.contenu,
                "auteur": str(message.auteur),
                "auteur_id": message.auteur_id,
                "date": timezone.localtime(message.created_at).strftime("%d/%m %H:%M"),
            },
        )
    except Exception:
        logger.warning("Diffusion WebSocket impossible", exc_info=True)


# ---------------------------------------------------------------- conversations


class MesConversationsView(ListeFrontView):
    model = Conversation
    roles = []
    titre = "Messagerie"
    template_name = "messaging/conversations.html"

    def get_queryset(self):
        user = self.request.user
        return (
            Conversation.objects.filter(participants=user)
            .prefetch_related("participants")
            .select_related("reservation")
            .annotate(
                dernier=Max("messages__created_at"),
                non_lus=Count("messages", filter=Q(messages__lu=False) & ~Q(messages__auteur=user)),
            )
            .order_by("-dernier", "-created_at")
        )


class ConversationDetailView(RoleRequiredMixin, View):
    template_name = "messaging/conversation.html"

    def get_conversation(self):
        # Filtrer sur les participants : changer l'id dans l'URL donne une 404, jamais la conversation d'un autre.
        return get_object_or_404(Conversation.objects.filter(participants=self.request.user), pk=self.kwargs["pk"])

    def afficher(self, conversation, form):
        user = self.request.user
        fil = [(m, texte_visible(m, user)) for m in conversation.messages.select_related("auteur")]
        return render(
            self.request,
            self.template_name,
            {
                "conversation": conversation,
                "fil": fil,
                "form": form,
                "interlocuteurs": conversation.interlocuteurs(user),
                "bloquee_par_moi": conversation.est_bloquee_pour(user),
            },
        )

    def get(self, request, pk):
        conversation = self.get_conversation()
        conversation.messages.filter(lu=False).exclude(auteur=request.user).update(lu=True)
        return self.afficher(conversation, MessageForm())

    def post(self, request, pk):
        conversation = self.get_conversation()
        if conversation.est_bloquee():
            messages.error(request, "Cette conversation est bloquée : aucun nouveau message ne peut être envoyé.")
            return redirect("messaging:conversation", pk=pk)
        form = MessageForm(request.POST, request.FILES)
        if not form.is_valid():
            return self.afficher(conversation, form)
        try:
            message = envoyer_message(
                conversation, request.user, form.cleaned_data["contenu"], form.cleaned_data.get("piece_jointe")
            )
        except ConversationBloquee:
            messages.error(request, "Cette conversation est bloquée.")
            return redirect("messaging:conversation", pk=pk)
        diffuser(message)
        if message.signale:
            messages.warning(
                request,
                f"Votre message a été signalé ({message.raison_signalement or 'modération'}) : "
                "il ne sera pas montré à votre interlocuteur. Les échanges et paiements se font sur CargoHub.",
            )
        return redirect(f"{reverse('messaging:conversation', args=[pk])}#dernier")


class ConversationBloquerView(RoleRequiredMixin, View):
    def post(self, request, pk):
        conversation = get_object_or_404(Conversation.objects.filter(participants=request.user), pk=pk)
        conversation.bloquee_par.add(request.user)
        messages.success(request, "Conversation bloquée.")
        return redirect("messaging:conversation", pk=pk)


class ConversationDebloquerView(RoleRequiredMixin, View):
    def post(self, request, pk):
        conversation = get_object_or_404(Conversation.objects.filter(participants=request.user), pk=pk)
        conversation.bloquee_par.remove(request.user)
        messages.success(request, "Conversation débloquée.")
        return redirect("messaging:conversation", pk=pk)


class NouvelleConversationView(RoleRequiredMixin, FormView):
    form_class = NouvelleConversationForm
    template_name = "messaging/nouvelle_conversation.html"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def get_initial(self):
        return {"reservation": self.request.GET.get("reservation")}

    def form_valid(self, form):
        reservation = form.cleaned_data["reservation"]
        interlocuteur = form.cleaned_data["interlocuteur"]
        if reservation:
            conversation = Conversation.objects.filter(reservation=reservation).first()
            if conversation is None:
                conversation = Conversation.objects.create(reservation=reservation)
            conversation.participants.add(reservation.expedition.pme, reservation.trajet.transporteur, self.request.user)
        else:
            conversation = (
                Conversation.objects.filter(reservation__isnull=True, participants=self.request.user)
                .filter(participants=interlocuteur)
                .first()
            )
            if conversation is None:
                conversation = Conversation.objects.create()
                conversation.participants.add(self.request.user, interlocuteur)
        message = envoyer_message(conversation, self.request.user, form.cleaned_data["contenu"])
        diffuser(message)
        if message.signale:
            messages.warning(self.request, "Votre message a été signalé par la modération.")
        return redirect("messaging:conversation", pk=conversation.pk)


class MessageSupprimerView(RoleRequiredMixin, View):
    """L'auteur supprime son propre message (POST uniquement)."""

    def post(self, request, pk):
        message = get_object_or_404(Message, pk=pk, auteur=request.user)
        conversation_id = message.conversation_id
        message.delete()
        messages.success(request, "Message supprimé.")
        return redirect("messaging:conversation", pk=conversation_id)


# ---------------------------------------------------------------- assistant et tickets


class AssistantSupportView(RoleRequiredMixin, FormView):
    """L'assistant IA répond tout de suite ; si la réponse ne suffit pas, l'utilisateur ouvre un ticket."""

    form_class = QuestionSupportForm
    template_name = "messaging/assistant.html"

    def form_valid(self, form):
        question = form.cleaned_data["question"]
        try:
            reponse, duree_ms = ai.mesurer(repondre_support, question)
        except Exception:
            logger.exception("Assistant de support en échec")
            reponse, duree_ms = None, None
            messages.error(self.request, "L’assistant est indisponible pour le moment. Ouvrez un ticket.")
        return self.render_to_response(
            self.get_context_data(
                form=form,
                question=question,
                reponse=reponse,
                duree_ms=duree_ms,
                ia_active=ai.disponible(),
                sans_reponse=reponse == REPONSE_PAR_DEFAUT,
            )
        )


class MesTicketsView(ListeFrontView):
    model = TicketSupport
    roles = []
    titre = "Mes tickets de support"
    template_name = "messaging/tickets.html"

    def get_queryset(self):
        return TicketSupport.objects.filter(auteur=self.request.user)


class MesTicketsMixin(RoleRequiredMixin):
    """Un utilisateur n'accède qu'à SES tickets (404 sinon)."""

    model = TicketSupport
    context_object_name = "ticket"

    def get_queryset(self):
        return TicketSupport.objects.filter(auteur=self.request.user)


class TicketCreerView(RoleRequiredMixin, CreateView):
    model = TicketSupport
    form_class = TicketForm
    template_name = "messaging/ticket_formulaire.html"

    def get_initial(self):
        return {"description": self.request.GET.get("description", "")}

    def form_valid(self, form):
        form.instance.auteur = self.request.user
        reponse = super().form_valid(form)
        try:
            repondre_ticket.delay(self.object.pk)
        except Exception:  # file Celery indisponible : le ticket est créé quand même
            logger.exception("Impossible de lancer la réponse automatique du ticket %s", self.object.pk)
        messages.success(
            self.request, "Ticket envoyé. L’assistant prépare une première réponse, un administrateur suivra."
        )
        return reponse

    def get_success_url(self):
        return reverse("messaging:ticket", args=[self.object.pk])


class TicketDetailView(MesTicketsMixin, DetailView):
    template_name = "messaging/ticket.html"


class TicketModifierView(MesTicketsMixin, UpdateView):
    form_class = TicketForm
    template_name = "messaging/ticket_formulaire.html"

    def get_queryset(self):
        return super().get_queryset().filter(statut=TicketSupport.Statut.OUVERT)

    def form_valid(self, form):
        messages.success(self.request, "Ticket modifié.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("messaging:ticket", args=[self.object.pk])


class TicketSupprimerView(MesTicketsMixin, DeleteView):
    template_name = "messaging/ticket_supprimer.html"
    success_url = reverse_lazy("messaging:tickets")

    def get_queryset(self):
        return super().get_queryset().filter(statut=TicketSupport.Statut.OUVERT)

    def form_valid(self, form):
        messages.success(self.request, "Ticket supprimé.")
        return super().form_valid(form)


# ---------------------------------------------------------------- back-office


class BackofficeTicketSupportView(ListeBackofficeView):
    model = TicketSupport
    titre = "Tickets de support"
    template_name = "messaging/backoffice/tickets.html"

    def get_queryset(self):
        qs = TicketSupport.objects.select_related("auteur", "assigne_a")
        if statut := self.request.GET.get("statut"):
            qs = qs.filter(statut=statut)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["statuts"] = TicketSupport.Statut.choices
        return ctx


class BackofficeTicketDetailView(AdminRequiredMixin, UpdateView):
    model = TicketSupport
    form_class = TraitementTicketForm
    template_name = "messaging/backoffice/ticket.html"
    context_object_name = "ticket"

    def get_initial(self):
        # Pré-remplit la réponse avec la suggestion de l'IA : l'admin relit et corrige.
        if not self.object.reponse_admin and self.object.reponse_ia:
            return {"reponse_admin": self.object.reponse_ia}
        return {}

    def form_valid(self, form):
        if form.cleaned_data["statut"] != TicketSupport.Statut.OUVERT and not form.cleaned_data["assigne_a"]:
            form.instance.assigne_a = self.request.user
        messages.success(self.request, "Ticket mis à jour.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("bo_messaging:ticket", args=[self.object.pk])


class BackofficeTicketSupprimerView(AdminRequiredMixin, DeleteView):
    model = TicketSupport
    template_name = "messaging/backoffice/ticket_supprimer.html"
    context_object_name = "ticket"
    success_url = reverse_lazy("bo_messaging:liste")

    def form_valid(self, form):
        messages.success(self.request, "Ticket supprimé.")
        return super().form_valid(form)


class BackofficeModerationView(ListeBackofficeView):
    model = Message
    titre = "Messages signalés"
    template_name = "messaging/backoffice/moderation.html"

    def get_queryset(self):
        return Message.objects.filter(signale=True).select_related("auteur", "conversation").order_by("-created_at")


class BackofficeModererMessageView(AdminRequiredMixin, View):
    """L'admin rétablit un message signalé à tort, ou le supprime."""

    def post(self, request, pk):
        message = get_object_or_404(Message, pk=pk, signale=True)
        if request.POST.get("action") == "retablir":
            message.signale = False
            message.raison_signalement = ""
            message.save(update_fields=["signale", "raison_signalement", "updated_at"])
            messages.success(request, "Message rétabli : il est de nouveau visible.")
        elif request.POST.get("action") == "supprimer":
            message.delete()
            messages.success(request, "Message supprimé.")
        else:
            messages.error(request, "Action inconnue.")
        return redirect("bo_messaging:moderation")
