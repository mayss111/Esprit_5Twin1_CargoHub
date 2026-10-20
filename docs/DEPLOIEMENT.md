# Déploiement sur Render

Le dépôt contient un **Blueprint** (`render.yaml`) qui crée en une fois :
le site (image Docker, HTTP + WebSockets), la base PostgreSQL et Redis. Le tout sur l'offre gratuite.

## Mise en ligne (une seule fois, par le responsable DevOps)

1. Pousser le projet sur GitHub (branche `main`).
2. Créer un compte sur https://render.com avec GitHub.
3. **New → Blueprint** → choisir le dépôt `cargohub` → **Apply**.
4. Render demande les valeurs secrètes (`AI_API_KEY`, clés Stripe) : les coller, ou laisser vide pour plus tard.
5. Attendre la fin du premier déploiement (5 à 10 minutes). Le site est sur `https://cargohub-xxxx.onrender.com`.
6. Créer l'administrateur et les données de démo : l'offre gratuite n'a pas de terminal, donc lancez-les depuis
   votre poste en vous connectant à la base de Render :
   ```bash
   # Render → cargohub-db → Connect → copier « External Database URL »
   DATABASE_URL="postgres://…" DJANGO_SETTINGS_MODULE=config.settings.prod SECRET_KEY=x python manage.py donnees_demo
   ```

## Déploiement continu (CI/CD)

```
Pull Request → CI GitHub (lint, tests, migrations, image Docker)
      ↓ fusion dans main
Render attend que la CI soit verte (autoDeployTrigger: checksPass) → reconstruit l'image → déploie
      ↓
Au démarrage du conteneur : migrations automatiques, puis serveur Daphne (docker/start.sh)
```

Aucune action manuelle : il suffit de fusionner dans `main`.

## Limites de l'offre gratuite (à connaître pour la soutenance)

| Limite | Conséquence | Solution |
|---|---|---|
| Le site s'endort après 15 min sans visite | La première page met environ 1 minute à s'afficher | Ouvrir le site 2 minutes avant la démo |
| La base PostgreSQL gratuite expire **30 jours** après sa création | Les données disparaissent | Recréer la base peu avant la soutenance, puis relancer `donnees_demo` |
| Pas de « background worker » gratuit | Celery tourne dans le même conteneur que le site (`RUN_CELERY_IN_WEB=1`) | Suffisant pour un projet étudiant |
| Les fichiers envoyés (photos, PDF) sont perdus à chaque redéploiement | Les médias ne sont pas conservés | Pour la démo, ce n'est pas bloquant ; sinon utiliser un stockage externe (Cloudinary, S3) |

Ces informations correspondent à l'offre de Render au moment de la création du projet (octobre 2026) : vérifiez https://render.com/docs/free si quelque chose a changé.

## En cas de problème

- **Render → cargohub → Logs** : les erreurs Python s'affichent ici.
- `DisallowedHost` → vérifier `ALLOWED_HOSTS` dans Render → Environment.
- Le déploiement ne part pas → la CI GitHub est-elle verte sur `main` ?
- Erreur de migration → la reproduire en local avec `docker compose up` (PostgreSQL, comme en production).
