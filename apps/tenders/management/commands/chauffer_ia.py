"""
python manage.py chauffer_ia

À lancer juste avant une démo : appelle une fois la suggestion de prix (scikit-learn) et une fois le LLM,
pour que les premiers clics du jury ne paient pas le temps de chargement. Affiche les deux durées.
"""

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.core import ai
from apps.tenders.ai import suggerer_prix


class Command(BaseCommand):
    help = "Prépare l'IA du M4 (scikit-learn + LLM) avant une démo et affiche les temps de réponse."

    def handle(self, *args, **options):
        resultat, ms = ai.mesurer(suggerer_prix, distance_km=160, poids_kg=300)
        self.stdout.write(f"Suggestion de prix : {ms} ms ({resultat['methode']}, {resultat['prix']} DT)")

        if not ai.disponible():
            self.stdout.write(self.style.WARNING("LLM : pas de clé AI_API_KEY, l’aide au choix utilisera la règle."))
            return
        try:
            _, ms = ai.mesurer(ai.demander, "Réponds simplement : OK")
        except ai.IAIndisponible as erreur:
            self.stdout.write(self.style.ERROR(f"LLM ({settings.AI_MODEL}) indisponible : {erreur}"))
            return
        self.stdout.write(self.style.SUCCESS(f"LLM ({settings.AI_MODEL}) : {ms} ms"))
