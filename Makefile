# Raccourcis communs à toute l'équipe (Linux / macOS / WSL / Git Bash).
.PHONY: up down logs shell migrate migrations superuser demo test cov ia lint format

up:            ## Lance toute l'application (site, base, Redis, Celery)
	docker compose up --build

down:
	docker compose down

logs:
	docker compose logs -f web

shell:
	docker compose exec web python manage.py shell

migrate:
	docker compose exec web python manage.py migrate

migrations:    ## make migrations app=shipments
	docker compose exec web python manage.py makemigrations $(app)

superuser:
	docker compose exec web python manage.py createsuperuser

demo:          ## Remplit la base avec des données de démonstration
	docker compose exec web python manage.py donnees_demo

test:
	docker compose exec web pytest

cov:           ## Tests + rapport de couverture (ouvrir htmlcov/index.html)
	docker compose exec web pytest --cov --cov-report=term --cov-report=html

ia:            ## Métriques des 5 parties IA
	docker compose exec web python manage.py evaluer_ia

lint:
	docker compose exec web ruff check .
	docker compose exec web ruff format --check .

format:
	docker compose exec web ruff check --fix .
	docker compose exec web ruff format .
