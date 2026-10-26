    """Classe les véhicules conformes du transporteur pour une mission donnée."""
    poids = Decimal(str(poids_kg))
    volume = Decimal(str(volume_m3))
    distance = Decimal(str(distance_km))
    vehicules = list(
        Vehicule.objects.filter(
            transporteur=transporteur,
            statut=Vehicule.Statut.ACTIF,
            conforme=True,
        )
        .prefetch_related("documents", "controles", "entretiens")
        .order_by("immatriculation")
    )

    facteurs = dict(FacteurEmission.objects.values_list("type_vehicule", "kg_co2_par_km"))
    candidats = []
    for vehicule in vehicules:
        if not vehicule.peut_publier_trajet() or vehicule.raisons_non_conformite():
            continue
        if poids > vehicule.capacite_kg or volume > vehicule.capacite_m3:
            continue

        utilisation_poids = float(poids / Decimal(vehicule.capacite_kg))
        utilisation_volume = float(volume / vehicule.capacite_m3)
        adequation = max(
            0,
            100
            * (
                1
                - 0.6 * abs(utilisation_poids - UTILISATION_CIBLE)
                - 0.4 * abs(utilisation_volume - UTILISATION_CIBLE)
            ),
        )

        facteur = Decimal(str(facteurs.get(vehicule.type, FACTEUR_EMISSION_PAR_DEFAUT)))
        co2 = distance * facteur * poids / Decimal(vehicule.capacite_kg)
        maintenance, prediction, statut_maintenance = _score_maintenance(vehicule, date_depart)
        candidats.append(
            {
                "vehicule": vehicule,
                "adequation": round(adequation, 1),
                "co2_kg": round(float(co2), 2),
                "maintenance": maintenance,
                "prediction": prediction,
                "statut_maintenance": statut_maintenance,
            }
        )

    if not candidats:
        return {
            "resultats": [],
            "message": (
                "Aucun véhicule actif et conforme ne peut transporter cette charge. "
                "Vérifiez les capacités, la conformité et les dates d'entretien de votre flotte."
            ),
        }

    co2_min = min(candidat["co2_kg"] for candidat in candidats)
    for candidat in candidats:
        candidat["emissions"] = round(100 * co2_min / candidat["co2_kg"], 1) if candidat["co2_kg"] else 100
        candidat["score"] = round(
            POIDS_ADEQUATION * candidat["adequation"]
            + POIDS_EMISSIONS * candidat["emissions"]
            + POIDS_MAINTENANCE * candidat["maintenance"],
            1,
        )
        candidat["date_entretien_prevue"] = candidat["prediction"]["date_prevue"]
        candidat["methode_maintenance"] = candidat["prediction"]["methode"]
        del candidat["prediction"]

    candidats.sort(key=lambda candidat: (-candidat["score"], candidat["co2_kg"], candidat["vehicule"].pk))
    return {
        "resultats": candidats,
        "message": "Classement calculé à partir de votre flotte et de son historique.",
    }
