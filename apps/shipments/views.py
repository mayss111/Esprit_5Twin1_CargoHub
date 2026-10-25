"""Pages PME du module Expéditions : liste, création, détail, modification, annulation."""

import json
from datetime import date

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.db.models import Case, IntegerField, Q, When
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.generic import DetailView, ListView

from apps.bookings.models import Notification
from apps.core.mixins import AdminRequiredMixin, RoleRequiredMixin
from apps.core.roles import Role, est_admin
from apps.warehouses.services.reservation import STATUTS_ELIGIBLES, depot_pour_affichage

from .forms import ImportExpeditionsForm, RegleInterditeForm, SaisieExpedition
from .models import Expedition, RegleInterdite
from .services.ai_checker import trancher_verification
from .services.ai_form_assistant import AssistantIndisponible, AssistantInvalide, analyser_description
from .services.bon_pdf import generer_pdf, jeton_bon, lire_jeton, url_verification
from .services.import_expeditions import contenu_xlsx, importer, message_bilan


def annoncer_verification(request, expedition, publier):
    if not publier and expedition.statut == Expedition.Statut.BROUILLON:
        messages.success(request, f"Le brouillon {expedition.reference} est enregistré.")
        return
    if expedition.statut == Expedition.Statut.PUBLIEE:
        messages.success(request, "Votre demande d'expédition a été vérifiée et publiée avec succès.")
    elif expedition.statut == Expedition.Statut.REFUSEE:
        messages.error(request, expedition.motif_decision)
    elif expedition.statut == Expedition.Statut.A_VERIFIER:
        messages.warning(request, "Votre expédition nécessite une vérification supplémentaire.")
    elif expedition.motif_decision:
        messages.error(request, expedition.motif_decision)
    else:
        messages.success(request, f"L'expédition {expedition.reference} est mise à jour.")


def filtrer_expeditions(queryset, request):
    """Recherche par référence, statut, villes et date. Les paramètres vides sont ignorés."""
    reference = request.GET.get("q", "").strip()
    if reference:
        queryset = queryset.filter(reference__icontains=reference)

    statut = request.GET.get("statut", "").strip()
    if statut in Expedition.Statut.values:
        queryset = queryset.filter(statut=statut)

    depart = request.GET.get("depart", "").strip()
    if depart:
        queryset = queryset.filter(adresse_depart__ville__icontains=depart)

    arrivee = request.GET.get("arrivee", "").strip()
    if arrivee:
        queryset = queryset.filter(adresse_arrivee__ville__icontains=arrivee)

    date_brute = request.GET.get("date", "").strip()
    if date_brute:
        try:
            jour = date.fromisoformat(date_brute)
            queryset = queryset.filter(Q(date_souhaitee=jour) | Q(date_arrivee=jour))
        except ValueError:
            pass
    return queryset


class ExpeditionAccesMixin(RoleRequiredMixin):
    """Une PME ne voit que ses propres expéditions. Les autres obtiennent une 404."""

    roles = [Role.PME]

    def get_queryset(self):
        return (
            Expedition.objects.filter(pme=self.request.user)
            .select_related("adresse_depart", "adresse_arrivee", "pme")
            .prefetch_related("articles", "controles")
        )

    def get_expedition(self, pk):
        return get_object_or_404(self.get_queryset(), pk=pk)


class MesExpeditionsView(ExpeditionAccesMixin, ListView):
    template_name = "shipments/liste.html"
    context_object_name = "expeditions"
    paginate_by = 20
    historique = False
    titre = "Mes expéditions"
    sous_titre = "Vos demandes d'envoi et leur statut."

    def get_queryset(self):
        queryset = super().get_queryset()
        if self.historique:
            aujourdhui = timezone.localdate()
            queryset = queryset.filter(
                Q(statut__in=[Expedition.Statut.RESERVEE, Expedition.Statut.LIVREE, Expedition.Statut.ANNULEE])
                | Q(date_arrivee__lt=aujourdhui)
            )
        else:
            queryset = queryset.exclude(statut=Expedition.Statut.ANNULEE)
        return filtrer_expeditions(queryset, self.request)

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        params = self.request.GET.copy()
        params.pop("page", None)
        get = self.request.GET
        contexte.update(
            titre=self.titre,
            sous_titre=self.sous_titre,
            historique=self.historique,
            statuts=[
                choix for choix in Expedition.Statut.choices if self.historique or choix[0] != Expedition.Statut.ANNULEE
            ],
            filtres=params.urlencode(),
            filtre={
                "q": get.get("q", ""),
                "statut": get.get("statut", ""),
                "depart": get.get("depart", ""),
                "arrivee": get.get("arrivee", ""),
                "date": get.get("date", ""),
            },
        )
        return contexte


class HistoriqueExpeditionsView(MesExpeditionsView):
    historique = True
    titre = "Historique des expéditions"
    sous_titre = "Expéditions passées, réservées, livrées ou annulées."


class CreerExpeditionView(ExpeditionAccesMixin, View):
    template_name = "shipments/formulaire.html"

    def get(self, request):
        return render(request, self.template_name, self._contexte(SaisieExpedition(pme=request.user)))

    def post(self, request):
        publier = "publier" in request.POST
        saisie = SaisieExpedition(request.POST, pme=request.user, publier=publier)
        if saisie.is_valid():
            expedition = saisie.save()
            annoncer_verification(request, expedition, publier)
            return redirect("shipments:detail", pk=expedition.pk)
        messages.error(request, "Corrigez les champs signalés avant d'enregistrer.")
        return render(request, self.template_name, self._contexte(saisie, publier))

    def _contexte(self, saisie, publier=False):
        return {"saisie": saisie, "publier": publier, "expedition": None, "titre": "Nouvelle expédition"}


class ImporterExpeditionsView(ExpeditionAccesMixin, View):
    """Import Excel. La publication passe par le même contrôleur que le formulaire."""

    def get(self, request):
        if request.GET.get("format") == "xlsx":
            reponse = HttpResponse(
                contenu_xlsx(),
                content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
            reponse["Content-Disposition"] = 'attachment; filename="modele-expeditions.xlsx"'
            return reponse
        return redirect("shipments:creer")

    def post(self, request):
        formulaire = ImportExpeditionsForm(request.POST, request.FILES)
        if not formulaire.is_valid():
            return self._page(request, formulaire.errors.get("fichier", []))
        crees, erreurs = importer(formulaire.cleaned_data["fichier"], request.user)
        if erreurs:
            messages.error(request, "Aucune expédition n'a été créée. Corrigez le fichier, puis importez-le à nouveau.")
            return self._page(request, erreurs)
        messages.success(request, message_bilan(crees))
        return redirect("shipments:liste")

    def _page(self, request, erreurs):
        return render(
            request,
            "shipments/formulaire.html",
            {
                "saisie": SaisieExpedition(pme=request.user),
                "publier": False,
                "expedition": None,
                "titre": "Nouvelle expédition",
                "erreurs_import": erreurs,
            },
        )


class DetailExpeditionView(ExpeditionAccesMixin, DetailView):
    template_name = "shipments/detail.html"
    context_object_name = "expedition"

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        contexte["jeton_bon"] = jeton_bon(self.object)
        contexte["depot"] = depot_pour_affichage(self.object)
        contexte["peut_reserver"] = self.object.statut in STATUTS_ELIGIBLES and contexte["depot"] is None
        return contexte


class ModifierExpeditionView(ExpeditionAccesMixin, View):
    template_name = "shipments/formulaire.html"

    def get(self, request, pk):
        expedition = self.get_expedition(pk)
        if not expedition.peut_etre_modifiee():
            messages.error(request, "Cette expédition ne peut plus être modifiée.")
            return redirect("shipments:detail", pk=expedition.pk)
        saisie = SaisieExpedition(expedition=expedition)
        return render(request, self.template_name, self._contexte(saisie, expedition))

    def post(self, request, pk):
        expedition = self.get_expedition(pk)
        if not expedition.peut_etre_modifiee():
            messages.error(request, "Cette expédition ne peut plus être modifiée.")
            return redirect("shipments:detail", pk=expedition.pk)
        publier = "publier" in request.POST
        saisie = SaisieExpedition(request.POST, expedition=expedition, publier=publier)
        if saisie.is_valid():
            expedition = saisie.save()
            annoncer_verification(request, expedition, publier)
            return redirect("shipments:detail", pk=expedition.pk)
        messages.error(request, "Corrigez les champs signalés avant d'enregistrer.")
        return render(request, self.template_name, self._contexte(saisie, expedition, publier))

    def _contexte(self, saisie, expedition, publier=False):
        return {
            "saisie": saisie,
            "publier": publier,
            "expedition": expedition,
            "titre": f"Modifier {expedition.reference}",
        }


class AnnulerExpeditionView(ExpeditionAccesMixin, View):
    def get(self, request, pk):
        expedition = self.get_expedition(pk)
        if not expedition.peut_etre_annulee():
            messages.error(request, "Cette expédition ne peut pas être annulée.")
            return redirect("shipments:detail", pk=expedition.pk)
        return render(
            request,
            "shipments/confirmer.html",
            {
                "expedition": expedition,
                "titre": "Annuler l'expédition",
                "question": f"Annuler {expedition.reference} ? Elle restera dans l'historique.",
                "action": "Annuler l'expédition",
            },
        )

    def post(self, request, pk):
        expedition = self.get_expedition(pk)
        if not expedition.peut_etre_annulee():
            messages.error(request, "Cette expédition ne peut pas être annulée.")
            return redirect("shipments:detail", pk=expedition.pk)
        expedition.statut = Expedition.Statut.ANNULEE
        expedition.save(update_fields=["statut", "updated_at"])
        messages.success(
            request,
            f"L'expédition {expedition.reference} est annulée. "
            "Elle n'apparaît plus dans la liste et reste dans l'historique.",
        )
        return redirect("shipments:historique")


class SupprimerExpeditionView(ExpeditionAccesMixin, View):
    """Une PME n'efface pas une demande. L'annulation la conserve dans l'historique."""

    def get(self, request, pk):
        return self._refuser(request, pk)

    def post(self, request, pk):
        return self._refuser(request, pk)

    def _refuser(self, request, pk):
        expedition = self.get_expedition(pk)
        messages.error(
            request,
            "Une demande ne peut pas être supprimée. Annulez-la : elle restera dans l'historique.",
        )
        return redirect("shipments:detail", pk=expedition.pk)


class BackofficeExpeditionView(AdminRequiredMixin, ListView):
    """Toutes les expéditions de la plateforme, avec recherche et filtres."""

    template_name = "shipments/backoffice_liste.html"
    context_object_name = "expeditions"
    paginate_by = 20

    def get_queryset(self):
        queryset = Expedition.objects.select_related(
            "pme", "pme__profil_pme", "adresse_depart", "adresse_arrivee"
        ).prefetch_related("articles")
        queryset = filtrer_expeditions(queryset, self.request)
        pme = self.request.GET.get("pme", "").strip()
        if pme:
            queryset = queryset.filter(Q(pme__email__icontains=pme) | Q(pme__profil_pme__raison_sociale__icontains=pme))
        return queryset

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        params = self.request.GET.copy()
        params.pop("page", None)
        get = self.request.GET
        contexte.update(
            statuts=Expedition.Statut.choices,
            filtres=params.urlencode(),
            filtre={
                "q": get.get("q", ""),
                "statut": get.get("statut", ""),
                "date": get.get("date", ""),
                "pme": get.get("pme", ""),
            },
        )
        return contexte


class BackofficeDetailExpeditionView(AdminRequiredMixin, DetailView):
    template_name = "shipments/backoffice_detail.html"
    context_object_name = "expedition"

    def get_queryset(self):
        return Expedition.objects.select_related(
            "pme", "pme__profil_pme", "adresse_depart", "adresse_arrivee"
        ).prefetch_related("articles", "controles")

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        contexte["jeton_bon"] = jeton_bon(self.object)
        contexte["depot"] = depot_pour_affichage(self.object)
        return contexte


class OuvrirNotificationView(LoginRequiredMixin, View):
    """Ouvre la notification de la PME connectée et la marque comme lue."""

    def get(self, request, pk):
        notification = get_object_or_404(Notification, pk=pk, destinataire=request.user)
        if not notification.lu:
            notification.lu = True
            notification.save(update_fields=["lu"])
        lien = notification.lien
        if lien.startswith("/") and not lien.startswith("//"):
            return redirect(lien)
        return redirect("shipments:liste")


class BackofficeVerificationsView(AdminRequiredMixin, ListView):
    """Expéditions refusées ou en attente d'un contrôle humain."""

    template_name = "shipments/backoffice_verifications.html"
    context_object_name = "expeditions"
    paginate_by = 20

    def get_queryset(self):
        queryset = (
            Expedition.objects.filter(statut__in=[Expedition.Statut.REFUSEE, Expedition.Statut.A_VERIFIER])
            .select_related("pme", "adresse_depart", "adresse_arrivee")
            .prefetch_related("controles")
        )
        queryset = filtrer_expeditions(queryset, self.request).filter(
            statut__in=[Expedition.Statut.REFUSEE, Expedition.Statut.A_VERIFIER]
        )
        email = self.request.GET.get("email", "").strip()[:254]
        if email:
            queryset = queryset.filter(pme__email__icontains=email)
        return queryset.order_by(
            Case(
                When(statut=Expedition.Statut.A_VERIFIER, then=0),
                default=1,
                output_field=IntegerField(),
            ),
            "-created_at",
        )

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        params = self.request.GET.copy()
        params.pop("page", None)
        get = self.request.GET
        visibles = self.get_queryset()
        contexte.update(
            nombre_a_verifier=visibles.filter(statut=Expedition.Statut.A_VERIFIER).count(),
            nombre_refusees=visibles.filter(statut=Expedition.Statut.REFUSEE).count(),
            recherche=any(get.get(nom) for nom in ("q", "email", "statut", "date")),
            filtres=params.urlencode(),
            filtre={
                "q": get.get("q", "")[:40],
                "email": get.get("email", "")[:254],
                "statut": get.get("statut", "")
                if get.get("statut")
                in {
                    Expedition.Statut.REFUSEE,
                    Expedition.Statut.A_VERIFIER,
                }
                else "",
                "date": get.get("date", "")[:10],
            },
        )
        return contexte


class BackofficeVerificationDecisionView(AdminRequiredMixin, View):
    """Accepte ou refuse une demande en attente de vérification."""

    def post(self, request, pk):
        decision = request.POST.get("decision")
        motif = request.POST.get("motif", "").strip()
        if decision == "refuser" and len(motif) < 10:
            messages.error(request, "Indiquez un motif de refus d'au moins 10 caractères.")
            return redirect("bo_shipments:verifications")
        if decision not in {"accepter", "refuser"}:
            messages.error(request, "Décision inconnue.")
            return redirect("bo_shipments:verifications")
        with transaction.atomic():
            expedition = get_object_or_404(
                Expedition.objects.select_for_update(),
                pk=pk,
                statut=Expedition.Statut.A_VERIFIER,
            )
            trancher_verification(expedition, acceptee=decision == "accepter", motif=motif)
        if decision == "accepter":
            messages.success(request, f"{expedition.reference} est acceptée et publiée.")
        else:
            messages.success(request, f"{expedition.reference} est refusée. La PME a été notifiée.")
        return redirect("bo_shipments:verifications")


class BackofficeInterdictionsView(AdminRequiredMixin, ListView):
    template_name = "shipments/backoffice_interdictions.html"
    context_object_name = "regles"

    def get_queryset(self):
        queryset = RegleInterdite.objects.all()
        terme = self.request.GET.get("q", "").strip()[:80]
        if terme:
            queryset = queryset.filter(
                Q(nom__icontains=terme) | Q(motif__icontains=terme) | Q(mots_cles__icontains=terme)
            )
        actif = self.request.GET.get("actif", "").strip()
        if actif == "1":
            queryset = queryset.filter(actif=True)
        elif actif == "0":
            queryset = queryset.filter(actif=False)
        return queryset

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        get = self.request.GET
        contexte.update(
            recherche=any(get.get(nom) for nom in ("q", "actif")),
            filtre={
                "q": get.get("q", "")[:80],
                "actif": get.get("actif", "") if get.get("actif") in {"0", "1"} else "",
            },
        )
        return contexte


class BackofficeInterdictionCreerView(AdminRequiredMixin, View):
    template_name = "shipments/backoffice_interdiction_formulaire.html"

    def get(self, request):
        return render(
            request, self.template_name, {"formulaire": RegleInterditeForm(), "titre": "Nouvelle interdiction"}
        )

    def post(self, request):
        formulaire = RegleInterditeForm(request.POST)
        if formulaire.is_valid():
            formulaire.save()
            messages.success(request, "La règle d'interdiction est enregistrée.")
            return redirect("bo_shipments:interdictions")
        return render(request, self.template_name, {"formulaire": formulaire, "titre": "Nouvelle interdiction"})


class BackofficeInterdictionModifierView(AdminRequiredMixin, View):
    template_name = "shipments/backoffice_interdiction_formulaire.html"

    def get(self, request, pk):
        regle = get_object_or_404(RegleInterdite, pk=pk)
        return render(
            request,
            self.template_name,
            {"formulaire": RegleInterditeForm(instance=regle), "titre": f"Modifier {regle.nom}"},
        )

    def post(self, request, pk):
        regle = get_object_or_404(RegleInterdite, pk=pk)
        formulaire = RegleInterditeForm(request.POST, instance=regle)
        if formulaire.is_valid():
            formulaire.save()
            messages.success(request, "La règle d'interdiction est mise à jour.")
            return redirect("bo_shipments:interdictions")
        return render(request, self.template_name, {"formulaire": formulaire, "titre": f"Modifier {regle.nom}"})


def _queryset_document():
    return Expedition.objects.select_related(
        "pme", "pme__profil_pme", "adresse_depart", "adresse_arrivee"
    ).prefetch_related("articles")


def _expedition_document(pk):
    return get_object_or_404(_queryset_document(), pk=pk)


class BonExpeditionView(LoginRequiredMixin, View):
    """Télécharge le bon PDF. Ne crée pas d'expédition."""

    def get(self, request, pk):
        expedition = _expedition_document(pk)
        if not (est_admin(request.user) or expedition.pme_id == request.user.pk):
            return HttpResponseForbidden("Vous ne pouvez pas télécharger ce document.")
        if not expedition.bon_disponible():
            return HttpResponseForbidden(
                "Le bon d'expédition n'est disponible que pour une expédition publiée et autorisée."
            )
        pdf = generer_pdf(expedition, url_verification(request, expedition))
        reponse = HttpResponse(pdf, content_type="application/pdf")
        reponse["Content-Disposition"] = f'attachment; filename="bon-{expedition.reference}.pdf"'
        return reponse


class VerifierBonView(View):
    """Page ouverte par le QR Code. Le jeton ne transporte pas les adresses."""

    template_name = "shipments/verifier_bon.html"

    def get(self, request, jeton):
        pk = lire_jeton(jeton)
        expedition = _queryset_document().filter(pk=pk).first() if pk else None
        complet = False
        lien = ""
        if expedition is not None and request.user.is_authenticated:
            if est_admin(request.user):
                complet = True
                lien = reverse("bo_shipments:detail", args=[expedition.pk])
            elif expedition.pme_id == request.user.pk:
                complet = True
                lien = reverse("shipments:detail", args=[expedition.pk])
        return render(
            request,
            self.template_name,
            {
                "valide": expedition is not None,
                "expedition": expedition if complet else None,
                "reference": expedition.reference if expedition else "",
                "statut": expedition.get_statut_display() if expedition else "",
                "code_statut": expedition.statut if expedition else "",
                "lien_detail": lien,
            },
        )


class AssistantSaisieView(ExpeditionAccesMixin, View):
    """Propose des champs. L'expédition n'est enregistrée que par le formulaire existant."""

    def post(self, request):
        try:
            corps = json.loads(request.body.decode() or "{}")
        except json.JSONDecodeError:
            return JsonResponse({"erreur": "Requête invalide."}, status=400)
        try:
            resultat = analyser_description(corps.get("description"), request.user.pk)
        except AssistantInvalide as exc:
            return JsonResponse({"erreur": str(exc)}, status=400)
        except AssistantIndisponible as exc:
            return JsonResponse({"erreur": str(exc)}, status=503)
        return JsonResponse(resultat)
