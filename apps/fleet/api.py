"""API REST du module Flotte — ViewSets sous /api/fleet/ (JWT SimpleJWT).

Voir apps/fleet/README.md pour les exemples de requêtes.
"""

import logging

from django.db import transaction
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from apps.core.roles import est_admin
from apps.maintenance.models import Entretien

from . import services
from .models import DocumentVehicule, FacteurEmission, Trajet, Vehicule
from .permissions import EstAdmin, EstPME, EstTransporteur, ProprietaireOuAdmin
from .serializers import (
    DocumentVehiculeSerializer,
    EntretienSerializer,
    FacteurEmissionSerializer,
    ImpactSerializer,
    TrajetReduitSerializer,
    TrajetSerializer,
    VehiculeSerializer,
)

logger = logging.getLogger("cargohub.fleet")


class VehiculeViewSet(viewsets.ModelViewSet):
    """CRUD de la flotte — le transporteur ne voit que SES véhicules."""

    serializer_class = VehiculeSerializer
    permission_classes = [EstTransporteur, ProprietaireOuAdmin]

    def get_queryset(self):
        if est_admin(self.request.user):
            return Vehicule.objects.select_related("transporteur").prefetch_related("documents")
        return Vehicule.objects.filter(transporteur=self.request.user).prefetch_related("documents")

    def perform_create(self, serializer):
        vehicule = serializer.save(transporteur=self.request.user)
        logger.info("Véhicule %s créé par %s", vehicule.immatriculation, self.request.user.email)

    def destroy(self, request, *args, **kwargs):
        vehicule = self.get_object()
        if vehicule.trajets.exists():
            return Response(
                {"detail": "Ce véhicule est lié à des trajets et ne peut pas être supprimé."},
                status=status.HTTP_409_CONFLICT,
            )
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=["patch"], url_path="statut")
    def changer_statut(self, request, pk=None):
        """PATCH /api/fleet/vehicules/{id}/statut/ — ADMIN : valide ou refuse le véhicule."""
        if not est_admin(request.user):
            return Response({"detail": "Réservé aux administrateurs."}, status=status.HTTP_403_FORBIDDEN)
        vehicule = self.get_object()
        nouveau = request.data.get("statut")
        if nouveau not in Vehicule.Statut.values:
            return Response(
                {"statut": [f"Valeur invalide. Choix : {', '.join(Vehicule.Statut.values)}."]},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        vehicule.statut = nouveau
        vehicule.conforme = nouveau != Vehicule.Statut.NON_CONFORME
        vehicule.motif_non_conformite = (
            "" if vehicule.conforme else request.data.get("motif", "Refusé par l'administrateur")
        )
        vehicule.save(update_fields=["statut", "conforme", "motif_non_conformite"])
        logger.info("Statut du véhicule %s changé en %s par %s", vehicule.immatriculation, nouveau, request.user.email)
        return Response(VehiculeSerializer(vehicule).data)

    @action(detail=True, methods=["post"], permission_classes=[EstTransporteur, ProprietaireOuAdmin])
    def documents(self, request, pk=None):
        """POST /api/fleet/vehicules/{id}/documents/ — ajoute carte grise ou assurance."""
        vehicule = self.get_object()
        serializer = DocumentVehiculeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            DocumentVehicule.objects.filter(vehicule=vehicule, type=serializer.validated_data["type"]).delete()
            serializer.save(vehicule=vehicule)
            vehicule.recalculer_conformite()
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["get"], permission_classes=[EstAdmin])
    def non_conformes(self, request):
        """GET /api/fleet/vehicules/non_conformes/ — ADMIN : véhicules bloqués + raisons."""
        vehicules = [v for v in self.get_queryset() if v.statut == Vehicule.Statut.NON_CONFORME or v.est_non_conforme()]
        page = self.paginate_queryset(vehicules)
        donnees = VehiculeSerializer(page if page is not None else vehicules, many=True).data
        source = page if page is not None else vehicules
        for v, d in zip(source, donnees, strict=False):
            d["raisons"] = v.raisons_non_conformite()
        if page is not None:
            return self.get_paginated_response(donnees)
        return Response(donnees)

    @action(detail=True, methods=["get"], permission_classes=[EstTransporteur, ProprietaireOuAdmin])
    def impact(self, request, pk=None):
        """GET /api/fleet/vehicules/{id}/impact/ — bilan CO₂ (certificat via /certificat/)."""
        vehicule = self.get_object()
        debut = request.query_params.get("debut")
        fin = request.query_params.get("fin")
        trajets = Trajet.objects.filter(vehicule=vehicule, statut=Trajet.Statut.TERMINE)
        if debut:
            trajets = trajets.filter(date_depart__date__gte=debut)
        if fin:
            trajets = trajets.filter(date_depart__date__lte=fin)
        co2 = sum((t.co2_kg or 0) for t in trajets)
        return Response(
            ImpactSerializer(
                {"nb_trajets": trajets.count(), "co2_total_kg": round(co2, 2), "points_eco": int(co2 // 100)}
            ).data
        )

    @action(detail=True, methods=["get"], permission_classes=[EstTransporteur, ProprietaireOuAdmin])
    def certificat(self, request, pk=None):
        """GET /api/fleet/vehicules/{id}/certificat/?debut=&fin= — télécharge le PDF vert."""
        vehicule = self.get_object()
        fin = timezone.localdate()
        debut = fin.replace(month=1, day=1)
        contenu, bilan = services.generer_certificat_vert(vehicule.transporteur, debut, fin)
        reponse = HttpResponse(contenu, content_type="application/pdf")
        reponse["Content-Disposition"] = f'attachment; filename="certificat-vert-{vehicule.pk}.pdf"'
        return reponse


class TrajetViewSet(viewsets.ModelViewSet):
    """CRUD des trajets + recherche compatible pour les PME (module Matching M4)."""

    serializer_class = TrajetSerializer
    permission_classes = [EstTransporteur, ProprietaireOuAdmin]

    def _recherche_compatible(self):
        """True si Matching (M4) : /compatibles/ ou GET /trajets/?compatible=..."""
        if self.action == "compatibles":
            return True
        return self.action == "list" and self.request.query_params.get("compatible") is not None

    def get_queryset(self):
        if self._recherche_compatible():
            return Trajet.objects.filter(statut=Trajet.Statut.PUBLIE).select_related("vehicule", "transporteur")
        if est_admin(self.request.user) and self.action == "list":
            return Trajet.objects.select_related("vehicule", "transporteur")
        return Trajet.objects.filter(transporteur=self.request.user).select_related("vehicule")

    def get_serializer_class(self):
        return TrajetReduitSerializer if self._recherche_compatible() else TrajetSerializer

    def get_permissions(self):
        if self._recherche_compatible():
            return [EstPME()]
        return super().get_permissions()

    def list(self, request, *args, **kwargs):
        if request.query_params.get("compatible") is not None:
            return self.compatibles(request)
        return super().list(request, *args, **kwargs)

    @transaction.atomic
    def perform_create(self, serializer):
        vehicule = serializer.validated_data["vehicule"]
        if vehicule.transporteur != self.request.user:
            raise PermissionDenied("Ce véhicule ne vous appartient pas.")
        if not vehicule.peut_publier_trajet():
            raise ValidationError("Véhicule non conforme ou en maintenance : publication impossible.")
        trajet = serializer.save(
            transporteur=self.request.user,
            capacite_totale_kg=serializer.validated_data["capacite_dispo_kg"],
            capacite_totale_m3=serializer.validated_data["capacite_dispo_m3"],
        )
        logger.info("Trajet #%s publié par %s", trajet.pk, self.request.user.email)

    @transaction.atomic
    def perform_update(self, serializer):
        """Refuse de réduire la capacité sous la part déjà réservée."""
        instance = serializer.save()
        if instance.capacite_dispo_kg < instance.capacite_reservee_kg:
            raise ValidationError("Impossible de réduire la capacité sous la part déjà réservée.")
        if instance.capacite_dispo_m3 < instance.capacite_reservee_m3:
            raise ValidationError("Impossible de réduire le volume sous la part déjà réservée.")

    def destroy(self, request, *args, **kwargs):
        trajet = self.get_object()
        if trajet.statut == Trajet.Statut.TERMINE:
            return Response(
                {"detail": "Un trajet terminé ne peut pas être annulé."}, status=status.HTTP_422_UNPROCESSABLE_ENTITY
            )
        trajet.statut = Trajet.Statut.ANNULE
        trajet.save(update_fields=["statut"])
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=["get"], url_path="compatibles")
    def compatibles(self, request):
        """GET /api/fleet/trajets/compatibles/?ville_depart=&ville_arrivee=&date=&poids_kg=&volume_m3=

        Recherche filtrée utilisée par le module Matching (Membre 4).
        """
        queryset = self.get_queryset()
        params = request.query_params
        compatible = params.get("compatible")
        if ville := params.get("ville_depart"):
            queryset = queryset.filter(ville_depart__icontains=ville)
        elif compatible and compatible.lower() not in {"1", "true", "oui", ""}:
            queryset = queryset.filter(ville_depart__icontains=compatible)
        if ville := params.get("ville_arrivee"):
            queryset = queryset.filter(ville_arrivee__icontains=ville)
        if date := params.get("date"):
            queryset = queryset.filter(date_depart__date=date)
        if poids := params.get("poids_kg"):
            queryset = queryset.filter(capacite_dispo_kg__gte=poids)
        if volume := params.get("volume_m3"):
            queryset = queryset.filter(capacite_dispo_m3__gte=volume)
        page = self.paginate_queryset(queryset)
        serializer = self.get_serializer_class()(page or queryset, many=True)
        return self.get_paginated_response(serializer.data) if page is not None else Response(serializer.data)


class EntretienViewSet(viewsets.ModelViewSet):
    """CRUD entretien — transporteur, sur ses propres véhicules."""

    serializer_class = EntretienSerializer
    permission_classes = [EstTransporteur, ProprietaireOuAdmin]

    def get_queryset(self):
        qs = Entretien.objects.select_related("vehicule")
        if est_admin(self.request.user):
            return qs
        return qs.filter(vehicule__transporteur=self.request.user)

    @transaction.atomic
    def perform_create(self, serializer):
        entretien = serializer.save()
        vehicule = entretien.vehicule
        if vehicule.statut == Vehicule.Statut.ACTIF and entretien.prochaine_echeance:
            pass  # la mise en maintenance reste manuelle ; la conformité est recalculée par la tâche
        vehicule.recalculer_conformite()


class FacteurEmissionViewSet(viewsets.ModelViewSet):
    """CRUD des facteurs d'émission — réservé à l'ADMIN (back-office)."""

    queryset = FacteurEmission.objects.all()
    serializer_class = FacteurEmissionSerializer

    def get_permissions(self):
        return [EstAdmin()]

    def perform_create(self, serializer):
        serializer.save()
        logger.info("Facteur d'émission %s modifié par %s", serializer.instance, self.request.user.email)
