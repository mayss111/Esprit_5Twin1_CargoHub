# CargoHub

Plateforme de **covoiturage de fret** : les PME réservent la place libre dans les camions des transporteurs indépendants déjà en route.
Projet d'équipe Django (5 membres) — front-office (PME, transporteurs) et back-office (administrateur), entièrement en Django.

| | |
|---|---|
| Python | **3.12** (fixé dans `.python-version` et le `Dockerfile`) |
| Django | **5.2 LTS** (support jusqu'en avril 2028) |
| Base de données | PostgreSQL 16 (Docker) — SQLite possible pour un test rapide |
| Temps réel / tâches | Django Channels (WebSockets), Celery + Redis |
| Interface | Templates Django + Bootstrap 5.3 |
| IA | API compatible OpenAI (Groq gratuit, ou Ollama en local) + scikit-learn |
| Déploiement | Render (Docker), CI/CD GitHub Actions |

---

## Démarrer (méthode recommandée : Docker)

Docker garantit que **les 5 membres ont exactement les mêmes versions** (Python, PostgreSQL, Redis, paquets).

1. Installer [Docker Desktop](https://www.docker.com/products/docker-desktop/) et Git.
2. Récupérer le projet et créer votre fichier de configuration :
   ```bash
   git clone <url-du-depot> cargohub && cd cargohub
   cp .env.example .env
   ```
3. Lancer l'application :
   ```bash
   docker compose up --build
   ```
4. Dans un **deuxième terminal**, créer les données de démonstration :
   ```bash
   docker compose exec web python manage.py donnees_demo
   ```
5. Ouvrir http://localhost:8000 — comptes de démo (mot de passe `cargohub2026`) :
   - `admin@cargohub.tn` → back-office : http://localhost:8000/backoffice/
   - `sami@atelier.tn` → PME
   - `karim@transport.tn` → transporteur

Raccourcis : `make up`, `make test`, `make lint`, `make migrations app=shipments` (voir `Makefile`).

## Démarrer sans Docker (dépannage uniquement)

```bash
python3.12 -m venv .venv
source .venv/bin/activate          # Windows : .venv\Scripts\activate
pip install -r requirements/dev.txt
cp .env.example .env               # puis commentez DATABASE_URL et REDIS_URL
python manage.py migrate
python manage.py donnees_demo
python manage.py runserver
```

Sans `DATABASE_URL`, le projet utilise SQLite ; sans `REDIS_URL`, les tâches Celery s'exécutent directement.
Avant chaque Pull Request, testez quand même avec Docker (PostgreSQL), c'est ce qui tourne en production.

## Organisation du code

```
config/              réglages (base, dev, test, prod), URLs, ASGI, Celery
apps/core/           partagé : rôles, mixins d'accès, couche IA, menus, données de démo
apps/<module>/       une application par module : models, views, urls, ai.py, tests
templates/           base.html (front-office), backoffice/base.html, pages communes
static/              CSS et logo CargoHub
docs/                EQUIPE.md (règles), DEPLOIEMENT.md
```

| Membre | Applications |
|---|---|
| M1 — Utilisateurs & communication | `accounts`, `messaging`, `contracts` |
| M2 — PME & marchandises | `shipments`, `warehouses`, `insurance` |
| M3 — Transporteurs & véhicules | `fleet`, `maintenance`, `ecology` |
| M4 — Mise en relation | `bookings`, `tenders` |
| M5 — Livraison, paiement & pilotage | `tracking`, `payments`, `loyalty`, `dashboard` |

**À lire avant de coder : [docs/EQUIPE.md](docs/EQUIPE.md).**
