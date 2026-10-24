# Règles de l'équipe CargoHub

## 0. Mise en place du dépôt (une seule personne, une seule fois)

```bash
cd cargohub
git init -b main
git add . && git commit -m "chore: projet de départ CargoHub"
git remote add origin https://github.com/<organisation>/cargohub.git
git push -u origin main
git checkout -b develop && git push -u origin develop
```
Puis inviter les 4 autres membres (Settings → Collaborators), protéger `main` et `develop` (voir §2),
et remplacer `@membre1` … `@membre5` dans `.github/CODEOWNERS`.
Chaque membre fait ensuite : `git clone …`, `cp .env.example .env`, `docker compose up --build`.

## 1. Même version pour tout le monde

| Élément | Où c'est fixé | Règle |
|---|---|---|
| Python 3.12 | `.python-version`, `Dockerfile` | Ne pas changer sans accord de l'équipe |
| Paquets Python | `requirements/base.txt`, `requirements/dev.txt` | Toujours une version exacte `==` |
| PostgreSQL 16, Redis 7 | `docker-compose.yml` | Toujours travailler avec `docker compose` |
| Bootstrap 5.3.3, Bootstrap Icons 1.11.3 | `templates/base.html` | Pas d'autre framework CSS |
| Formatage du code | `pyproject.toml` (Ruff) | `make format` avant chaque commit |

**Ajouter une dépendance :**
1. Trouver la version : `pip index versions nom-du-paquet`
2. L'ajouter avec `==` dans `requirements/base.txt` (ou `dev.txt` pour un outil de dev), avec un commentaire indiquant le module.
3. Reconstruire : `docker compose up --build`
4. Le dire à l'équipe dans la Pull Request (case à cocher).

## 2. Git : branches et Pull Requests

```
main        ← version déployée (protégée, déploiement automatique sur Render)
develop     ← intégration de l'équipe (protégée)
feature/m2-estimation-prix   ← votre travail
```

1. Partir de `develop` à jour : `git checkout develop && git pull`
2. Créer une branche : `git checkout -b feature/m<numéro>-<sujet>`
3. Commits courts et clairs : `feat(shipments): estimation du prix`, `fix(bookings): capacité négative`
4. Pousser et ouvrir une Pull Request vers `develop`. La CI doit être verte et **1 autre membre** doit relire.
5. En fin de sprint, `develop` est fusionnée dans `main` → déploiement automatique.

**Protection des branches (à régler une fois dans GitHub → Settings → Branches)** : pour `main` et `develop`, exiger une Pull Request, 1 relecture et la réussite de la CI.

## 3. Les migrations (source n°1 de conflits)

- Vous ne créez des migrations **que pour vos applications** : `make migrations app=shipments`.
- Avant de créer une migration : `git pull` sur `develop` et `make migrate`.
- Ne modifiez jamais une migration déjà fusionnée dans `develop` : créez-en une nouvelle.
- Si deux migrations ont le même numéro après une fusion : `python manage.py makemigrations --merge`.
- Le modèle `Utilisateur` (M1) est partagé : toute modification passe par une Pull Request relue par 2 personnes.

## 4. Front-office et back-office

- **Front-office** (PME, transporteur) : héritez de `templates/base.html`, protégez vos vues avec
  `RoleRequiredMixin` et `roles = [Role.PME]` ou `[Role.TRANSPORTEUR]`.
- **Back-office** (admin) : héritez de `templates/backoffice/base.html`, protégez avec `AdminRequiredMixin`.
  Les URL sont sous `/backoffice/…` (préfixes dans `config/urls.py`).
- Une nouvelle page ? Ajoutez-la au menu dans `apps/core/context_processors.py`.
- Chaque app a déjà une page liste front-office et une page liste back-office (`views.py`) : partez de là.

## 5. La partie IA de chaque membre

Toutes les fonctions IA passent par `apps/core/ai.py` (même fournisseur, même clé pour toute l'équipe)
et ont un **mode de repli sans clé** : l'application et les tests marchent toujours, même sans Internet.

| Membre | Fichier | Fonctionnalité IA | Technique |
|---|---|---|---|
| M1 | `apps/messaging/ai.py` | Assistant de support (répond avant l'ouverture d'un ticket) + modération des messages | LLM |
| M2 | `apps/shipments/ai.py` | Saisie intelligente : la PME décrit son envoi en une phrase, l'IA remplit le formulaire et détecte les marchandises interdites | LLM |
| M3 | `apps/maintenance/ai.py` | Prédiction de la date du prochain entretien d'un camion | Machine learning (régression scikit-learn) |
| M4 | `apps/tenders/ai.py` | Suggestion du « prix juste » d'une offre à partir des offres passées | Machine learning (régression scikit-learn) |
| M5 | `apps/tracking/ai.py` | Analyse du sentiment des avis + résumé des avis d'un transporteur | LLM |

Les 5 fonctions existent déjà avec une première version testée (`apps/core/tests_ia.py`).
**À faire par chaque membre** : les brancher dans ses pages, améliorer les consignes (prompts) ou le modèle, et ajouter des tests.

**Obtenir une clé gratuite :** créer un compte sur https://console.groq.com, générer une clé, la mettre dans `AI_API_KEY` du `.env`.
Ne la partagez jamais dans Git. Le modèle est réglable avec `AI_MODEL` (vérifiez la liste des modèles disponibles sur la console Groq).
Pour travailler sans Internet : installer [Ollama](https://ollama.com), puis `AI_BASE_URL=http://host.docker.internal:11434/v1`, `AI_API_KEY=ollama`, `AI_MODEL=llama3.2`.

## 6. Tests et qualité

- Chaque membre écrit les tests de ses modules dans `apps/<module>/tests.py` (pytest).
- Les données de test communes (PME, transporteur, trajet, expédition…) sont dans `conftest.py`.
- `make test` et `make lint` doivent passer avant chaque Pull Request ; la CI les relance automatiquement.
- Une fois : `pip install pre-commit && pre-commit install` → vérification automatique à chaque commit.

## 7. DevOps : qui fait quoi

| Élément | Fichier | Responsable |
|---|---|---|
| Environnement Docker | `Dockerfile`, `docker-compose.yml` | Toute l'équipe (Sprint 0), ensuite M5 |
| CI (lint, tests, migrations, image Docker) | `.github/workflows/ci.yml` | M5 |
| Déploiement Render | `render.yaml`, `docs/DEPLOIEMENT.md` | M5 |
| Relectures par module | `.github/CODEOWNERS` | Chacun pour ses modules |

Pensez à remplacer `@membre1` … `@membre5` dans `.github/CODEOWNERS` par les vrais pseudos GitHub.

## 8. Grille de validation finale : où se trouve chaque critère

> ⚠️ **Pas de Git → note individuelle divisée par 2. Pas d'intégration + déploiement → note d'équipe = 0.**
> Chacun commite avec SON compte GitHub, régulièrement (le jury regarde l'historique).

| Critère (points) | Ce qui est déjà dans le projet | Ce que CHAQUE membre doit faire |
|---|---|---|
| **CRUD (2)** | Pages liste front + back | Créer / modifier / supprimer / détail sur ses entités, validation des formulaires (serveur + `required`, `min`… côté client), messages de succès |
| **Tests unitaires (0,75)** | `conftest.py`, tests des services et de l'IA | Tests de ses modèles (validations, contraintes) et de sa logique métier |
| **Tests d'intégration (0,75)** | Toutes les pages testées par rôle | Tests de ses vues : statut HTTP, données affichées, formulaire POST valide / invalide |
| **Couverture (0,5)** | `make cov` → `htmlcov/index.html` ; rapport aussi dans GitHub → Actions → « couverture » | Garder ses apps au-dessus de 80 % |
| **Sécurité (0,75)** | CSRF actif, ORM uniquement, mots de passe hachés, `DEBUG=False` en prod, secrets dans `.env` | Ne jamais écrire de SQL brut ni de clé dans le code |
| **Rôles / permissions (0,75)** | `RoleRequiredMixin`, `AdminRequiredMixin`, tests 403 et redirection | Protéger chaque nouvelle vue ; filtrer `get_queryset()` sur l'utilisateur (une PME ne voit QUE ses données, même en changeant l'id dans l'URL) + un test pour le prouver |
| **Robustesse (0,5)** | Pages 403 / 404 / 500 personnalisées | `get_object_or_404`, `try/except` autour des appels externes (IA, Stripe), messages d'erreur clairs |
| **Accessibilité (2)** | `<header>/<nav>/<main>/<footer>`, lien « Aller au contenu », focus visible, `aria-label` sur les boutons-icônes, contrastes AA | Dans ses pages : un seul `<h1>`, `<label>` sur chaque champ, `alt` sur chaque image, `aria-label` sur les boutons sans texte ; passer **Lighthouse** (Chrome → F12 → Lighthouse → Accessibilité) et faire une capture du score |
| **IA — intégration (2)** | Clé dans `.env`, repli sans clé, `ai.mesurer()`, spinner `data-ia` | Brancher sa fonction IA dans une vraie page (vue dédiée) avec `<form data-ia="Analyse en cours…">` et un message clair si l'IA échoue |
| **IA — métriques et performance (2)** | `python manage.py evaluer_ia` (F1, matrice de confusion, MAE, R², temps de réponse) | Agrandir SON jeu de test dans `apps/core/evaluation/jeux.py` (30 à 50 exemples), commenter les chiffres à l'oral ; si l'appel LLM dépasse ~1 s → le lancer en tâche Celery (voir ci-dessous) |
| **UX/UI (1)** | Charte CargoHub, Bootstrap, menus responsive | Vérifier ses pages sur téléphone (F12 → mode mobile) |
| **QCM / questions (8)** | — | Savoir expliquer : architecture, sécurité, choix de l'IA, CI/CD, Docker |

### Appel IA long → Celery (performance)
Pour M1 (réponse du support) et M5 (résumé des avis), l'appel au LLM prend 1 à 3 secondes :
1. Créer une tâche `@shared_task` dans `apps/<module>/tasks.py` qui appelle la fonction IA et **enregistre le résultat en base** (ex. champ `resume_ia` du profil, ou `reponse_ia` du ticket).
2. Dans la vue : `ma_tache.delay(objet.pk)` puis rediriger tout de suite avec le message « Analyse en cours… ».
3. La page affiche le résultat dès qu'il est enregistré (rafraîchissement, ou WebSocket comme dans `tracking`).
Sans Redis (tests, sans Docker), Celery exécute la tâche directement : rien à changer.
