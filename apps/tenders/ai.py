"""
Partie IA du Membre 4 — Suggestion du « prix juste » pour une offre.

Quand un transporteur répond à un appel d'offres, CargoHub lui suggère un prix.
Un modèle de régression (scikit-learn) est entraîné sur les offres RETENUES
du passé (distance, poids → prix). Avec trop peu de données : formule de base.
"""

from decimal import Decimal

from .models import Offre

PRIX_KM_TONNE = 0.35  # DT par km et par tonne (formule de repli)
PRIX_MINIMUM = 30  # DT


def _formule(distance_km: float, poids_kg: float) -> float:
    return max(PRIX_MINIMUM, distance_km * (poids_kg / 1000) * PRIX_KM_TONNE + 20)


def suggerer_prix(distance_km: float, poids_kg: float) -> dict:
    """Renvoie {"prix": Decimal, "methode": str}."""
    historique = [
        (o.trajet.distance_km, float(o.appel.expedition.poids_total_kg), float(o.prix))
        for o in Offre.objects.filter(statut=Offre.Statut.RETENUE, trajet__distance_km__isnull=False)
        .select_related("trajet", "appel__expedition")
        .prefetch_related("appel__expedition__articles")[:500]
    ]
    if len(historique) >= 10:
        from sklearn.linear_model import LinearRegression

        modele = LinearRegression().fit([[d, p] for d, p, _ in historique], [prix for *_, prix in historique])
        prix = float(modele.predict([[distance_km, poids_kg]])[0])
        methode = f"régression sur {len(historique)} offres"
    else:
        prix, methode = _formule(distance_km, poids_kg), "formule"
    return {"prix": Decimal(max(prix, PRIX_MINIMUM)).quantize(Decimal("0.01")), "methode": methode}
