"""
Métriques des 5 parties IA, à présenter au jury (grille : « Validation et performance »).

    python manage.py evaluer_ia            # les 5 membres
    python manage.py evaluer_ia --membre m4

- Classification (M1, M2, M5) : exactitude, précision, rappel, F1, matrice de confusion.
- Régression (M3, M4) : erreur moyenne absolue (MAE), R², comparée à une règle simple.
- Temps de réponse moyen de chaque fonction.
Sans AI_API_KEY, ce sont les modes de repli qui sont évalués (indiqué dans le rapport).
"""

import random
from datetime import date, timedelta
from statistics import mean

from django.core.management.base import BaseCommand

from apps.core import ai
from apps.core.evaluation import jeux


class Command(BaseCommand):
    help = "Calcule les métriques des parties IA (classification, régression, temps de réponse)."

    def add_arguments(self, parser):
        parser.add_argument("--membre", choices=["m1", "m2", "m3", "m4", "m5"])

    def handle(self, *args, membre=None, **options):
        mode = "LLM (" + ai.settings.AI_MODEL + ")" if ai.disponible() else "mode de repli (pas de AI_API_KEY)"
        self.stdout.write(self.style.MIGRATE_HEADING(f"Évaluation IA — {mode}"))
        for code in ["m1", "m2", "m3", "m4", "m5"]:
            if membre in (None, code):
                getattr(self, code)()

    # ---------- outils ----------
    def titre(self, texte):
        self.stdout.write("\n" + self.style.SUCCESS(texte))

    def classification(self, attendus, predits, temps):
        from sklearn.metrics import accuracy_score, confusion_matrix, precision_recall_fscore_support

        etiquettes = sorted(set(attendus) | set(predits), key=str)
        p, r, f1, _ = precision_recall_fscore_support(attendus, predits, average="macro", zero_division=0)
        self.stdout.write(f"  Exemples : {len(attendus)}   Exactitude : {accuracy_score(attendus, predits):.0%}")
        self.stdout.write(f"  Précision : {p:.2f}   Rappel : {r:.2f}   F1 : {f1:.2f}   (moyenne macro)")
        self.stdout.write(f"  Matrice de confusion (lignes = attendu, colonnes = prédit) : {etiquettes}")
        for nom, ligne in zip(etiquettes, confusion_matrix(attendus, predits, labels=etiquettes), strict=True):
            self.stdout.write(f"    {str(nom):<13} {[int(x) for x in ligne]}")
        self.stdout.write(f"  Temps de réponse moyen : {mean(temps):.0f} ms")

    def regression(self, reels, predits, base, nom_base):
        from sklearn.metrics import mean_absolute_error, r2_score

        self.stdout.write(f"  Exemples de test : {len(reels)}")
        self.stdout.write(
            f"  Modèle : MAE = {mean_absolute_error(reels, predits):.1f}   R² = {r2_score(reels, predits):.2f}"
        )
        self.stdout.write(
            f"  {nom_base} : MAE = {mean_absolute_error(reels, base):.1f}   R² = {r2_score(reels, base):.2f}"
        )

    # ---------- membres ----------
    def m1(self):
        from apps.messaging.ai import moderer

        self.titre("M1 — Modération des messages (classification signalé / non signalé)")
        resultats = [ai.mesurer(moderer, texte) for texte, _ in jeux.MODERATION]
        self.classification(
            [attendu for _, attendu in jeux.MODERATION],
            [bool(r["signale"]) for r, _ in resultats],
            [ms for _, ms in resultats],
        )

    def m2(self):
        from apps.shipments.ai import analyser_description

        self.titre("M2 — Saisie intelligente (classification du type de marchandise)")
        resultats = [ai.mesurer(analyser_description, texte) for texte, *_ in jeux.EXPEDITIONS]
        self.classification(
            [typ for _, typ, _ in jeux.EXPEDITIONS],
            [r["type_marchandise"] for r, _ in resultats],
            [ms for _, ms in resultats],
        )
        interdits = [(r["interdit"], att) for (r, _), (*_, att) in zip(resultats, jeux.EXPEDITIONS, strict=True)]
        trouves = sum(1 for pred, att in interdits if att and pred)
        self.stdout.write(f"  Marchandises interdites détectées : {trouves}/{sum(1 for _, a in interdits if a)}")

    def m3(self):
        from apps.maintenance.ai import INTERVALLE_KM, predire_depuis_historique

        self.titre("M3 — Prédiction du prochain entretien (régression)")
        self.stdout.write(
            "  Données simulées : 200 camions, 5 entretiens chacun ; on prédit le 5e à partir des 4 premiers."
        )
        hasard = random.Random(42)
        reels, predits, base, temps = [], [], [], []
        for _ in range(200):
            km_jour, jour, km, historique = hasard.uniform(60, 300), date(2025, 1, 1), 50_000, []
            for _ in range(5):
                historique.append((jour, round(km)))
                duree = INTERVALLE_KM / (km_jour * hasard.uniform(0.8, 1.2))
                jour, km = jour + timedelta(days=round(duree)), km + INTERVALLE_KM
            prediction, millisecondes = ai.mesurer(predire_depuis_historique, historique[:4])
            reels.append((historique[4][0] - historique[3][0]).days)
            predits.append((prediction["date_prevue"] - historique[3][0]).days)
            base.append(180)
            temps.append(millisecondes)
        self.stdout.write("  Erreur exprimée en jours entre le dernier entretien et le suivant :")
        self.regression(reels, predits, base, "Règle « tous les 6 mois »")
        self.stdout.write(f"  Temps de prédiction moyen : {mean(temps):.1f} ms (200 véhicules simulés)")

    def m4(self):
        from apps.tenders.ai import _formule, caracteristiques, entrainer, suggerer_prix
        from apps.tenders.models import Offre

        self.titre("M4 — Suggestion du prix juste (régression)")
        reelles = [
            (o.trajet.distance_km, float(o.appel.expedition.poids_total_kg), float(o.prix))
            for o in Offre.objects.filter(statut=Offre.Statut.RETENUE, trajet__distance_km__isnull=False)
            .select_related("trajet", "appel__expedition")
            .prefetch_related("appel__expedition__articles")
        ]
        if len(reelles) >= 30:
            donnees = reelles
            self.stdout.write(f"  Données réelles : {len(donnees)} offres retenues.")
        else:
            hasard = random.Random(42)
            donnees = []
            for _ in range(300):
                d, p = hasard.uniform(20, 500), hasard.uniform(50, 5000)
                prix = 25 + 0.32 * d * p / 1000 + 0.04 * d + hasard.gauss(0, 12)
                donnees.append((d, p, max(prix, 30)))
            self.stdout.write("  Données simulées : 300 offres (moins de 30 offres retenues en base).")
        random.Random(1).shuffle(donnees)
        coupe = int(len(donnees) * 0.8)
        entrainement, test = donnees[:coupe], donnees[coupe:]
        modele = entrainer(entrainement)
        predits = list(modele.predict([caracteristiques(d, p) for d, p, _ in test]))
        self.stdout.write(f"  Découpage : {len(entrainement)} pour l'entraînement, {len(test)} pour le test (80/20).")
        self.stdout.write("  Erreur exprimée en dinars (DT) :")
        self.regression([prix for *_, prix in test], predits, [_formule(d, p) for d, p, _ in test], "Formule fixe")
        _, ms = ai.mesurer(suggerer_prix, distance_km=160, poids_kg=300)
        self.stdout.write(f"  Temps de réponse de suggerer_prix : {ms} ms")
        self.m4b()

    def m4b(self):
        from collections import Counter

        from apps.tenders.ai import recommander_depuis_resume

        self.titre("M4b — Aide au choix d'une offre (accord avec le choix d'un humain)")
        accords, temps, methodes = 0, [], Counter()
        for offres, attendu in jeux.RECOMMANDATIONS:
            resume = [
                {
                    "offre_id": numero,
                    "transporteur": f"Transporteur {numero}",
                    "prix": prix,
                    "prix_juste": juste,
                    "ecart_pct": round((prix - juste) / juste * 100, 1),
                    "note": note,
                    "depart": (date.today() + timedelta(days=jours)).isoformat(),
                }
                for numero, (prix, juste, note, jours) in enumerate(offres, start=1)
            ]
            resultat, ms = ai.mesurer(recommander_depuis_resume, resume)
            accords += resultat["offre_id"] == attendu
            temps.append(ms)
            methodes[resultat["methode"]] += 1
        total = len(jeux.RECOMMANDATIONS)
        self.stdout.write(
            f"  Exemples : {total}   Accord avec le choix humain : {accords}/{total} ({accords / total:.0%})"
        )
        self.stdout.write(f"  Temps de réponse moyen : {mean(temps):.0f} ms")
        self.stdout.write("  Méthode : " + ", ".join(f"{m} ({n})" for m, n in methodes.items()))

    def m5(self):
        from apps.tracking.ai import analyser_sentiment

        self.titre("M5 — Sentiment des avis (classification POSITIF / NEUTRE / NEGATIF)")
        resultats = [ai.mesurer(analyser_sentiment, texte, note) for texte, note, _ in jeux.AVIS]
        self.classification(
            [attendu for *_, attendu in jeux.AVIS],
            [str(r) for r, _ in resultats],
            [ms for _, ms in resultats],
        )
