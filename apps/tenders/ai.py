"""
Partie IA du Membre 4.

1. suggerer_prix(distance, poids) : le « prix juste » d'une offre.
   Un modèle de régression (scikit-learn) est entraîné sur les offres RETENUES
   du passé (distance, poids → prix). Avec trop peu de données : formule de base.
2. recommander_offre(appel) : aide la PME à choisir parmi les offres reçues.
   Un LLM compare prix, écart au prix juste, note du transporteur et date de départ.
   Sans clé ou si l'IA échoue : une règle simple (écart au prix juste + note).
"""

import json
import re
from decimal import Decimal

from django.db.models import Avg

from apps.core import ai

from .models import Offre

PRIX_KM_TONNE = 0.35  # DT par km et par tonne (formule de repli)
PRIX_MINIMUM = 30  # DT


def _formule(distance_km: float, poids_kg: float) -> float:
    return max(PRIX_MINIMUM, distance_km * (poids_kg / 1000) * PRIX_KM_TONNE + 20)


def caracteristiques(distance_km: float, poids_kg: float) -> list[float]:
    """Variables du modèle. Le prix dépend surtout de « distance × tonnes » (comme la formule)."""
    return [distance_km, poids_kg, distance_km * poids_kg / 1000]


def entrainer(historique: list) -> object:
    """Entraîne la régression sur [(distance, poids, prix), …] — utilisée aussi par `evaluer_ia`."""
    from sklearn.linear_model import LinearRegression

    return LinearRegression().fit([caracteristiques(d, p) for d, p, _ in historique], [prix for *_, prix in historique])


def chauffer_modele():
    """Importe scikit-learn et fait un entraînement de chauffe sur 2 points fictifs (appelé au démarrage)."""
    return entrainer([(100.0, 1000.0, 55.0), (200.0, 2000.0, 160.0)])


def estimateur():
    """Renvoie (fonction distance, poids → prix, méthode). Le modèle est entraîné une seule fois."""
    historique = [
        (o.trajet.distance_km, float(o.appel.expedition.poids_total_kg), float(o.prix))
        for o in Offre.objects.filter(statut=Offre.Statut.RETENUE, trajet__distance_km__isnull=False)
        .select_related("trajet", "appel__expedition")
        .prefetch_related("appel__expedition__articles")[:500]
    ]
    if len(historique) >= 10:
        modele = entrainer(historique)

        def estimer(distance_km, poids_kg):
            return max(float(modele.predict([caracteristiques(distance_km, poids_kg)])[0]), PRIX_MINIMUM)

        return estimer, f"régression sur {len(historique)} offres"
    return _formule, "formule"


def suggerer_prix(distance_km: float, poids_kg: float) -> dict:
    """Renvoie {"prix": Decimal, "methode": str}."""
    estimer, methode = estimateur()
    return {"prix": Decimal(estimer(distance_km, poids_kg)).quantize(Decimal("0.01")), "methode": methode}


# ---------------------------------------------------------------- aide au choix d'une offre

SANS_AVIS = "pas encore d'avis"

CONSIGNE_RECOMMANDATION = (
    "Tu aides une PME tunisienne à choisir un transporteur parmi plusieurs offres pour une expédition. "
    "Pour chaque offre tu reçois : transporteur (son nom), prix (DT), prix_juste (estimation du marché), "
    "ecart_pct (écart du prix au prix juste, négatif = moins cher que le marché), note (moyenne des avis des "
    f"clients sur 5, ou « {SANS_AVIS} ») et depart (date de départ du camion). "
    "Choisis l'offre au meilleur rapport prix / fiabilité : un prix bas compte, mais une mauvaise note ou un départ "
    "beaucoup plus tardif que les autres sont des risques. Dans l'explication, désigne TOUJOURS une offre par le nom "
    "de son transporteur (« l'offre de Karim »), jamais par son numéro offre_id. "
    'Format : {"offre_id": <entier>, "explication": "3 phrases maximum en français simple, sans jargon"}'
)


def notes_des_avis(transporteurs) -> dict:
    """Note moyenne des avis reçus (module tracking, lecture seule) : {id du transporteur: moyenne sur 5}."""
    from apps.tracking.models import Avis

    moyennes = Avis.objects.filter(cible__in=transporteurs).values("cible").annotate(moyenne=Avg("note"))
    return {m["cible"]: round(float(m["moyenne"]), 1) for m in moyennes}


def resumer_offres(appel) -> list[dict]:
    """Ce que l'IA (ou la règle) voit de chaque offre encore proposée."""
    offres = list(appel.offres.filter(statut=Offre.Statut.PROPOSEE).select_related("trajet", "transporteur"))
    notes = notes_des_avis([o.transporteur_id for o in offres])
    poids = float(appel.expedition.poids_total_kg)
    estimer, _ = estimateur()
    resume = []
    for o in offres:
        juste = round(estimer(o.trajet.distance_km, poids), 2) if o.trajet and o.trajet.distance_km else None
        note = notes.get(o.transporteur_id)  # None = pas encore d'avis
        resume.append(
            {
                "offre_id": o.pk,
                "transporteur": str(o.transporteur),
                "prix": float(o.prix),
                "prix_juste": juste,
                "ecart_pct": round((float(o.prix) - juste) / juste * 100, 1) if juste else None,
                "note": note,
                "depart": o.trajet.date_depart.date().isoformat() if o.trajet else None,
            }
        )
    return resume


def _score(offre: dict) -> float:
    """Plus petit = meilleur : écart au prix juste (en %), moins 10 points par étoile au-dessus de 3."""
    ecart = offre["ecart_pct"] if offre["ecart_pct"] is not None else 0
    bonus = (offre["note"] - 3) * 10 if offre["note"] is not None else 0
    return ecart - bonus


def _nombre(valeur: float) -> str:
    """Écriture française : 144,6 et non 144.6."""
    return f"{valeur:g}".replace(".", ",")


def recommander_par_regle(resume: list[dict]) -> dict:
    meilleure = min(resume, key=lambda o: (_score(o), o["prix"]))
    prix = _nombre(meilleure["prix"])
    phrases = [f"L’offre de {meilleure['transporteur']} à {prix} DT a le meilleur rapport prix / fiabilité."]
    if meilleure["ecart_pct"] is not None:
        sens = "sous le" if meilleure["ecart_pct"] <= 0 else "au-dessus du"
        ecart, juste = _nombre(abs(meilleure["ecart_pct"])), _nombre(meilleure["prix_juste"])
        phrases.append(f"Elle est {ecart} % {sens} prix juste estimé ({juste} DT).")
    if meilleure["note"] is not None:
        phrases.append(f"Le transporteur a une note de {_nombre(meilleure['note'])}/5.")
    else:
        phrases.append("Le transporteur n’a pas encore de note.")
    return {"offre_id": meilleure["offre_id"], "explication": " ".join(phrases), "methode": "règle"}


def recommander_depuis_resume(resume: list[dict]) -> dict:
    """LLM si disponible ; sinon, ou si sa réponse est inutilisable, la règle. Renvoie toujours la méthode."""
    if not resume:
        raise ValueError("Aucune offre à comparer.")
    pour_le_llm = [{**o, "note": SANS_AVIS if o["note"] is None else o["note"]} for o in resume]
    try:
        reponse = ai.demander_json(
            "Offres reçues :\n" + json.dumps(pour_le_llm, ensure_ascii=False), systeme=CONSIGNE_RECOMMANDATION
        )
    except ai.IAIndisponible:
        return recommander_par_regle(resume)
    noms = {o["offre_id"]: o["transporteur"] for o in resume}
    offre_id, explication = reponse.get("offre_id"), str(reponse.get("explication") or "").strip()
    if isinstance(offre_id, str) and offre_id.isdigit():
        offre_id = int(offre_id)
    if offre_id not in noms or not explication:  # l'IA a inventé une offre ou n'a rien expliqué
        resultat = recommander_par_regle(resume)
        resultat["methode"] = "règle (réponse de l’IA inutilisable)"
        return resultat
    return {
        "offre_id": offre_id,
        "explication": sans_identifiants(explication, noms)[:600],
        "methode": f"LLM ({ai.settings.AI_MODEL})",
    }


# « l'offre 63 », « L’offre n° 63 », « offre #63 », « offre_id 63 »…
IDENTIFIANT_OFFRE = re.compile(r"\b(?:([Ll])['’]\s*)?offre(?:_id)?\s*(?:n[°o]\.?\s*|#\s*|id\s*:?\s*)?(\d+)\b")


def sans_identifiants(texte: str, noms: dict) -> str:
    """Remplace par sécurité tout numéro technique d’offre par « l’offre de <nom> » (jamais visible du jury)."""

    def remplacer(m):
        nom = noms.get(int(m.group(2)))
        if nom is None:
            return m.group(0)
        debut = f"{m.group(1)}’offre" if m.group(1) else "offre"
        return f"{debut} de {nom}"

    return IDENTIFIANT_OFFRE.sub(remplacer, texte)


def recommander_offre(appel) -> dict:
    """{"offre_id": int, "explication": str, "methode": str} pour un appel d'offres ayant des offres proposées."""
    return recommander_depuis_resume(resumer_offres(appel))
