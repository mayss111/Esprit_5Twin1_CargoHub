# CargoHub SPA (frontend)

SPA React (Vite) qui consomme l'API REST Django `/api/…` en JWT.

## Pages du module Flotte (M3 — Lakhdher)

| Route | Page |
|---|---|
| `/connexion` | Connexion (JWT) |
| `/flotte` | Ma flotte — CRUD véhicules + upload carte grise / assurance |
| `/trajets` | Mes trajets — publication (capacité plafonnée au véhicule), taux de remplissage, carte Leaflet des départs/arrivées |
| `/entretien` | Maintenance — saisie des entretiens (rappels automatiques côté serveur) |
| `/impact` | Impact écologique — graphique CO₂ (Recharts) + téléchargement du certificat vert PDF |

## Démarrage

```bash
cd frontend
npm install
npm run dev      # http://localhost:5173 (proxy /api → Django :8000)
```

## Conventions

- Couleurs de marque : orange `#F5A623`, bleu marine `#1B2A4A` (voir `src/styles.css`).
- Validation **côté client ET côté serveur** : les erreurs DRF (`422`) sont affichées champ par champ en français (`messageErreur` dans `api.js`).
- Jetons JWT stockés dans `localStorage` (`cargohub-jeton`, `cargohub-refresh`), rafraîchis automatiquement.
- Composants responsive (mobile-first).
