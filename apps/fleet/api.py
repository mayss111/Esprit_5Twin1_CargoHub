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
        vehicule.save(update_fields=["statut", "conforme", "motif_non_conformite", "updated_at"])
        logger.info(
            "Statut du véhicule %s changé en %s par %s",
            vehicule.immatriculation,
            nouveau,
            request.user.email,
        )
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
