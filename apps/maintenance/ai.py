"""
Partie IA du Membre 3 — Prédiction du prochain entretien (machine learning).

À partir de l'historique des entretiens d'un camion (date, kilométrage),
un modèle de régression (scikit-learn) apprend combien de kilomètres le
camion fait par jour, et prédit la date à laquelle il atteindra le
prochain seuil d'entretien. Sans historique suffisant : règle simple.
"""

from datetime import date, timedelta

INTERVALLE_KM = 10_000  # vidange tous les 10 000 km (à ajuster)


def predire_prochain_entretien(vehicule, aujourd_hui: date | None = None) -> dict:
    """Renvoie {"date_prevue", "km_prevu", "methode"}."""
    historique = list(vehicule.entretiens.order_by("date").values_list("date", "kilometrage"))
    return predire_depuis_historique(historique, aujourd_hui)


def predire_depuis_historique(historique: list, aujourd_hui: date | None = None) -> dict:
    """Même prédiction à partir d'une liste [(date, km), …] triée — utilisée aussi par `evaluer_ia`."""
    aujourd_hui = aujourd_hui or date.today()
    if not historique:
        return {"date_prevue": aujourd_hui + timedelta(days=180), "km_prevu": INTERVALLE_KM, "methode": "règle"}

    dernier_km = historique[-1][1]
    km_prevu = dernier_km + INTERVALLE_KM

    if len(historique) >= 3:
        from sklearn.linear_model import LinearRegression

        origine = historique[0][0]
        x = [[(d - origine).days] for d, _ in historique]
        y = [km for _, km in historique]
        modele = LinearRegression().fit(x, y)
        km_par_jour = float(modele.coef_[0])
        if km_par_jour > 0:
            jours = (km_prevu - modele.intercept_) / km_par_jour
            return {
                "date_prevue": origine + timedelta(days=round(jours)),
                "km_prevu": km_prevu,
                "methode": "régression linéaire",
            }

    return {"date_prevue": historique[-1][0] + timedelta(days=180), "km_prevu": km_prevu, "methode": "règle"}
