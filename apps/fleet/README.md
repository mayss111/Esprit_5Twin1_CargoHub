# Module 3 — Transporteurs & Véhicules (apps/fleet)

Moduleowned par **Lakhdher** : gestion de flotte, trajets, conformité, impact écologique et API REST consommée par le SPA React et le module Matching (M4).

## Modèles

| Modèle | Rôle |
|---|---|
| `Vehicule` | type, immatriculation (unique), capacités, statut (`ACTIF` / `EN_MAINTENANCE` / `NON_CONFORME`) |
| `DocumentVehicule` | carte grise / assurance, fichier (PDF/JPEG/PNG ≤ 5 Mo), date d'expiration |
| `Trajet` | publication d'un trajet, capacité restante, `est_compatible(expedition)` |
| `EtapeTrajet` | villes intermédiaires |
| `FacteurEmission` | kg CO₂/km par type de véhicule (administrable) |

Un véhicule dont un document ou le contrôle technique est expiré passe automatiquement `NON_CONFORME` et ne peut plus publier de trajets.

La carte transporteur peut calculer des itinéraires routiers et proposer jusqu'à deux alternatives via Valhalla. Les camions, frigorifiques et semi-remorques utilisent le profil poids lourd ; les camionnettes utilisent le profil voiture. Les routes sont calculées entre les coordonnées approximatives des centres-villes (le modèle ne stocke pas encore d'adresses de chargement/déchargement), sans trafic en temps réel ni dimensions individuelles du véhicule. L'instance Valhalla publique convient à la démonstration ; un déploiement à fort trafic devrait utiliser un service dédié ou auto-hébergé.

## Planificateur IA

La page transporteur `/flotte/assistant-ia/` classe les véhicules adaptés à une
mission selon trois critères explicables : adéquation de capacité (55 %), CO₂
estimé (25 %) et risque d'entretien à la date prévue (20 %). La prévision
d'entretien réutilise le modèle de régression de `apps/maintenance/ai.py` ; si
l'historique est trop court, le classement indique qu'il utilise une estimation
prudente. Les véhicules non conformes, en maintenance ou trop petits sont
écartés. Aucun appel externe ni clé IA n'est nécessaire, et la planification
n'affecte pas le véhicule ni ne crée de trajet.

## API REST (JWT SimpleJWT)

Authentification :

```http
POST /api/token/            {"email": "...", "password": "..."}  → {"access", "refresh"}
POST /api/token/refresh/    {"refresh": "..."}
```

### Transporteur (front-office)

| Méthode & route | Description |
|---|---|
| `GET/POST /api/fleet/vehicules/` | liste (paginée) / création véhicule |
| `GET/PUT/PATCH/DELETE /api/fleet/vehicules/{id}/` | détail / modification / suppression |
| `PATCH /api/fleet/vehicules/{id}/statut/` | **ADMIN** — valider / marquer non conforme `{"statut": "NON_CONFORME", "motif": "..."}` |
| `POST /api/fleet/vehicules/{id}/documents/` | upload carte grise ou assurance (multipart) |
| `GET /api/fleet/vehicules/non_conformes/` | **ADMIN** — véhicules bloqués + raisons |
| `GET /api/fleet/vehicules/{id}/impact/?debut=2026-01-01&fin=2026-12-31` | bilan CO₂ + points éco |
| `GET /api/fleet/vehicules/{id}/certificat/` | télécharge le certificat vert (PDF) |
| `GET/POST /api/fleet/trajets/` | liste / publication (capacité plafonnée au véhicule) |
| `DELETE /api/fleet/trajets/{id}/` | annulation (le trajet passe `ANNULE`) |
| `GET /api/fleet/entretiens/` + POST | suivi entretien |
| `CRUD /api/fleet/facteurs-emission/` | **ADMIN** — facteurs CO₂ |
| `CRUD /api/admin/facteurs-emission/` | alias back-office des facteurs CO₂ |

### PME (module Matching M4)

```http
GET /api/fleet/trajets/compatibles/?ville_depart=Monastir&ville_arrivee=Tunis&date=2026-11-02&poids_kg=250&volume_m3=1
GET /api/fleet/trajets/?compatible=Monastir&ville_arrivee=Tunis&poids_kg=250
Authorization: Bearer <jeton PME>
```

Réponse paginée `{"count": n, "results": [...]}`. Service Python équivalent : `apps.fleet.services.trajets_compatibles(expedition)` et `trajet.est_compatible(expedition)`.

## Erreurs standardisées

- `401` jeton absent/invalide · `403` rôle insuffisant · `404` objet d'un autre transporteur
- `422` validation : `{"erreurs": {"capacite_dispo_kg": ["La capacité dépasse celle du véhicule."]}}` ou `{"detail": "message métier"}`

## Tâches Celery (beat quotidien)

- `apps.fleet.tasks.verifier_conformite_flotte` — bloque les véhicules non conformes + notifications
- `apps.fleet.tasks.notifier_alerte_documents` — email + notification à J-30 avant expiration
- `apps.fleet.tasks.notifier_alerte_entretien` — rappel à J-7
- `apps.fleet.tasks.generer_certificat_vert(transporteur_id, ...)` — PDF du bilan CO₂

## CO₂

`emissions = distance_km × facteur(type) × (charge / capacité)` — facteurs modifiables par l'admin, points éco = CO₂ ÷ 100 (transmis au module Fidélité M5).

## Tests

```bash
pytest apps/fleet            # modèles, services, CO₂, certificat
pytest apps/fleet --cov      # couverture
```

Données de démo : `python manage.py donnees_demo` (comptes `karim@transport.tn` / `admin@cargohub.tn`, mot de passe `cargohub2026`).
