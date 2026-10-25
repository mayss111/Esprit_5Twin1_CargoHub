"""Partie IA du Membre 3 (flotte) — planificateur : quel véhicule pour quelle mission ?

Le classement combine adéquation de capacité, émissions estimées et
disponibilité prédite par l'IA de maintenance. Il reste explicable et fonctionne
sans fournisseur externe ni clé API.
"""

from decimal import Decimal

from django.utils import timezone

from apps.maintenance.ai import predire_prochain_entretien

from .models import FacteurEmission, Vehicule

POIDS_ADEQUATION = 0.55
POIDS_EMISSIONS = 0.25
POIDS_MAINTENANCE = 0.20
UTILISATION_CIBLE = 0.80
FACTEUR_EMISSION_PAR_DEFAUT = Decimal("0.2500")


def _score_maintenance(vehicule, date_depart):
    entretiens = list(vehicule.entretiens.order_by("date").values_list("date", "kilometrage"))
    prediction = predire_prochain_entretien(vehicule, timezone.localdate())

    # En l'absence d'au moins trois points, la prédiction est une règle de
    # repli : on conserve un score neutre et l'interface signale l'incertitude.
    if len(entretiens) < 3 or prediction["methode"] != "régression linéaire":
        return 70, prediction, "Historique limité : estimation prudente"

    jours_restants = (prediction["date_prevue"] - date_depart).days
    if jours_restants < 0:
        score = 0
        statut = "Entretien prédit avant ce départ"
    elif jours_restants <= 7:
        score = 35
        statut = "Entretien prédit dans les 7 jours suivant ce départ"
    elif jours_restants <= 30:
        score = 60
        statut = "Entretien à planifier dans le mois"
    elif jours_restants <= 60:
        score = 80
        statut = "Entretien à surveiller dans les 2 mois"
    else:
        score = 100
        statut = "Aucun entretien proche détecté"
    return score, prediction, statut


def recommander_vehicules(transporteur, poids_kg, volume_m3, distance_km, date_depart):
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
                1 - 0.6 * abs(utilisation_poids - UTILISATION_CIBLE) - 0.4 * abs(utilisation_volume - UTILISATION_CIBLE)
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
    return {"resultats": candidats, "message": "Classement calculé à partir de votre flotte et de son historique."}
