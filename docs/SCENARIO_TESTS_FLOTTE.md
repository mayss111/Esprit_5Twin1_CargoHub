# Scénario de test manuel — Module 3 « Transporteurs & Véhicules »

> Objectif : parcourir **toutes les fonctionnalités** du module (flotte, trajets, conformité, entretien, CO₂, back-office, API) comme le ferait un utilisateur réel, et vérifier les règles métier à chaque étape.
>
> Deux façons de tester : via l'**interface** (templates Django + SPA React) ou via l'**API** (curl / Postman). Les deux sont décrites ci-dessous.

---

## 0. Préparation de l'environnement

```bash
docker compose up --build -d      # ou : python manage.py runserver + redis
python manage.py migrate          # (automatique dans Docker)
python manage.py donnees_demo     # comptes + données de démonstration
```

Comptes de démo (mot de passe : `cargohub2026`) :

| Rôle | Email | Utilisation |
|---|---|---|
| ADMIN | `admin@cargohub.tn` | back-office |
| TRANSPORTEUR | `karim@transport.tn` | espace flotte |
| PME | `sami@atelier.tn` | recherche de trajets |

Spa React (optionnel) :

```bash
cd frontend && npm install && npm run dev   # http://localhost:5173
```

---

## 1. Connexion / sécurité

| # | Action | Résultat attendu |
|---|---|---|
| 1.1 | Se connecter en tant que `karim@transport.tn` (transporteur) | Accès à l'espace transporteur |
| 1.2 | Ouvrir `/flotte/vehicules/` sans être connecté | Redirection vers la page de connexion |
| 1.3 | Se connecter en tant que `sami@atelier.tn` (PME) puis visiter `/flotte/vehicules/` | **403 / refus** : les PME n'ont pas accès à la flotte |

### Via l'API (JWT)

```bash
# Obtenir un jeton
curl -X POST http://localhost:8000/api/token/ \
  -H "Content-Type: application/json" \
  -d '{"email": "karim@transport.tn", "password": "cargohub2026"}'
# → {"access": "...", "refresh": "..."}

# Sans jeton → 401
curl -i http://localhost:8000/api/fleet/vehicules/
# → HTTP/1.1 401 Unauthorized

# Avec jeton → 200
curl http://localhost:8000/api/fleet/vehicules/ -H "Authorization: Bearer <ACCESS>"
```

---

## 2. Gestion de la flotte (transporteur)

| # | Action | Résultat attendu |
|---|---|---|
| 2.1 | Créer un véhicule : type `CAMION`, immatriculation `999 TU 1111`, 2000 kg, 12 m³ | Véhicule créé, statut `ACTIF` |
| 2.2 | Recréer le **même** immatriculation | Erreur : « immatriculation existe déjà » (422 en API) |
| 2.3 | Saisir `capacite_kg = 0` ou `capacite_m3 = -1` | Erreur de validation claire en français |
| 2.4 | Téléverser la **carte grise** (PDF) expirant dans 6 mois | Document accepté, véhicule reste conforme |
| 2.5 | Téléverser une **assurance** expirant dans 10 jours | Document accepté (alerte planifiée, pas de blocage) |
| 2.6 | Téléverser un fichier `.exe` ou une image de 10 Mo | Refus : format non autorisé / dépasse 5 Mo |
| 2.7 | Se connecter avec un **autre** transporteur et ouvrir le véhicule de Karim | 404 : chaque transporteur ne voit que SA flotte |

### Via l'API

```bash
# Création
curl -X POST http://localhost:8000/api/fleet/vehicules/ \
  -H "Authorization: Bearer <ACCESS>" -H "Content-Type: application/json" \
  -d '{"type": "CAMION", "immatriculation": "999 TU 1111", "capacite_kg": 2000, "capacite_m3": "12"}'

# Upload d'un document (multipart)
curl -X POST http://localhost:8000/api/fleet/vehicules/1/documents/ \
  -H "Authorization: Bearer <ACCESS>" \
  -F "type=ASSURANCE" -F "fichier=@assurance.pdf" -F "date_expiration=2027-06-30"

# Document expiré côté validation → 422
#   date_expiration = hier  →  "La date d'expiration doit être dans le futur."
```

---

## 3. Publication de trajets

| # | Action | Résultat attendu |
|---|---|---|
| 3.1 | Publier un trajet avec le camion `999 TU 1111` : Sousse → Tunis, demain 08:00, 1500 kg, 10 m³, 90 DT | Trajet créé, statut `PUBLIE`, capacités totales figées (1500 / 10) |
| 3.2 | Essayer `capacite_dispo_kg = 5000` (> capacité du véhicule 2000) | Refus : « La capacité dépasse celle du véhicule » |
| 3.3 | Essayer une date de départ **dans le passé** | Refus : « La date de départ doit être dans le futur » |
| 3.4 | Publier un trajet avec le véhicule d'un **autre** transporteur | 403 : « Ce véhicule ne vous appartient pas » |
| 3.5 | Vérifier le taux de remplissage d'un trajet sans réservation | 0 % |
| 3.6 | Annuler un trajet publié | Statut devient `ANNULE` (pas de suppression physique) |

### Via l'API

```bash
curl -X POST http://localhost:8000/api/fleet/trajets/ \
  -H "Authorization: Bearer <ACCESS>" -H "Content-Type: application/json" \
  -d '{"vehicule": 2, "ville_depart": "Sousse", "ville_arrivee": "Tunis",
       "date_depart": "2026-11-02T08:00:00Z", "capacite_dispo_kg": "1500",
       "capacite_dispo_m3": "10", "prix_indicatif": "90"}'

# Sur-capacité → 422
#   {"erreurs": {"capacite_dispo_kg": ["La capacité dépasse celle du véhicule."]}}
```

---

## 4. Réservation et baisse de capacité (intégration M4)

| # | Action | Résultat attendu |
|---|---|---|
| 4.1 | En tant que PME (`sami@atelier.tn`), publier une expédition Monastir → Tunis, 250 kg / 1 m³, date = même jour que le trajet | Expédition `PUBLIEE` |
| 4.2 | Rechercher les trajets compatibles (cf. commande 5.1) | Le trajet Karim apparaît |
| 4.3 | Réserver puis faire **accepter** la réservation (par Karim ou via le module Réservations) | `capacite_dispo_kg` du trajet **diminue de 250** ; taux de remplissage > 0 |
| 4.4 | Réserver 5000 kg sur le même trajet | Refus : « Capacité insuffisante sur ce trajet » (anti-surbooking) |
| 4.5 | Remplir complètement le trajet | Statut passe à `COMPLET` |
| 4.6 | Annuler une réservation acceptée | La capacité est **rendue**, statut repasse à `PUBLIE` |
| 4.7 | Karim tente de réduire `capacite_dispo_kg` **sous** la part déjà réservée | Refus : « Impossible de réduire la capacité sous la part déjà réservée » (422) |

---

## 5. Recherche compatible (utilisé par le module Matching M4)

```bash
# Jeton PME requis
curl "http://localhost:8000/api/fleet/trajets/compatibles/?ville_depart=Monastir&ville_arrivee=Tunis&date=2026-11-02&poids_kg=250&volume_m3=1" \
  -H "Authorization: Bearer <JETON_PME>"
# → 200 {"count": 1, "results": [ ... trajet Karim ... ]}

# Même requête avec jeton TRANSPORTEUR → 403 (réservé aux PME)
# Ville sans trajet (Gabès) → count = 0
```

---

## 6. Conformité : blocage automatique

| # | Action | Résultat attendu |
|---|---|---|
| 6.1 | Modifier en base la date d'expiration de l'assurance de `999 TU 1111` à **hier** (`django-admin` ou shell) | Rien ne change tant que la vérification n'a pas tourné |
| 6.2 | Lancer la tâche : `python manage.py shell -c "from apps.fleet.tasks import verifier_conformite_flotte; print(verifier_conformite_flotte.delay())"` (ou attendre le beat quotidien) | Véhicule passe `NON_CONFORME`, motif = « Assurance expiré le jj/mm/aaaa », notification in-app créée pour Karim |
| 6.3 | Karim essaie de **publier un trajet** avec ce véhicule | Refus : « Impossible de publier un trajet : le véhicule est non conforme (…). » |
| 6.4 | Les trajets compatibles du véhicule non conforme disparaissent de la recherche PME | `est_compatible()` renvoie False |
| 6.5 | Renouveler l'assurance (nouveau document valide) et relancer la tâche | Véhicule repasse `ACTIF`, publication à nouveau possible |
| 6.6 | Enregistrer un **contrôle technique** expiré/défavorable (module Entretien) puis relancer la tâche | Blocage à nouveau, motif « Contrôle technique expiré ou défavorable » |

### Via l'API (back-office)

```bash
# L'admin marque un véhicule non conforme
curl -X PATCH http://localhost:8000/api/fleet/vehicules/2/statut/ \
  -H "Authorization: Bearer <JETON_ADMIN>" -H "Content-Type: application/json" \
  -d '{"statut": "NON_CONFORME", "motif": "Documents illisibles"}'

# Karim tente la même chose → 403
```

---

## 7. Entretien et alertes Celery

| # | Action | Résultat attendu |
|---|---|---|
| 7.1 | Karim enregistre un entretien : vidange, aujourd'hui, 120 000 km, 85 DT, prochaine échéance dans 6 mois | Entretien visible dans la liste |
| 7.2 | Lancer `notifier_alerte_entretien.delay()` avec un entretien dont l'échéance est dans 5 jours | Notification in-app « Entretien à prévoir » pour Karim |
| 7.3 | Lancer `notifier_alerte_documents.delay()` avec l'assurance expirant dans 10 jours | Notification + **email** (console en dev) |
| 7.4 | Vérifier `celerybeat-schedule` / logs du worker | Les 3 tâches quotidiennes sont bien planifiées |

---

## 8. Impact écologique et certificat vert

| # | Action | Résultat attendu |
|---|---|---|
| 8.1 | Vérifier les facteurs par défaut en base : camionnette 0.18, camion 0.25, semi-remorque 0.41, frigorifique 0.33 | Créés par `donnees_demo` |
| 8.2 | Marquer un trajet `TERMINE` (distance 100 km, capacité 3000 kg, charge réservée 1000 kg) | CO₂ = 100 × 0.25 × (1000/3000) = **8.33 kg** |
| 8.3 | Ouvrir `/api/fleet/vehicules/{id}/impact/` | `{"nb_trajets": 1, "co2_total_kg": 8.33, "points_eco": 0}` |
| 8.4 | Accumuler ≥ 100 kg de CO₂ | Points éco = CO₂ ÷ 100 (ex. 250 kg → 2 pts) — valeur à destination du module Fidélité (M5) |
| 8.5 | Télécharger `/api/fleet/vehicules/{id}/certificat/` | Fichier PDF valide (en-tête `%PDF`), bandeau bleu marine + titre orange, période, trajets, CO₂, points |
| 8.6 | Modifier le facteur camion à **0.31** (admin) et recalculer | Le CO₂ du prochain calcul utilise 0.31 |

### Via l'API (facteurs — admin)

```bash
curl -X POST http://localhost:8000/api/fleet/facteurs-emission/ \
  -H "Authorization: Bearer <JETON_ADMIN>" -H "Content-Type: application/json" \
  -d '{"type_vehicule": "CAMION", "kg_co2_par_km": "0.31"}'

# Karim → 403
```

---

## 9. Back-office (admin)

| # | Action | Résultat attendu |
|---|---|---|
| 9.1 | Se connecter en `admin@cargohub.tn`, ouvrir le back-office véhicules | Liste de TOUS les véhicules, filtres statut/type |
| 9.2 | **Valider** un véhicule en attente (statut `ACTIF`) | Statut appliqué, action tracée dans les logs |
| 9.3 | **Rejeter** un véhicule (`NON_CONFORME` + motif) | Le véhicule ne peut plus publier |
| 9.4 | Ouvrir la liste des véhicules **non conformes** (`/api/fleet/vehicules/non_conformes/`) | Véhicules bloqués + raisons détaillées |
| 9.5 | Ouvrir le tableau de bord | Nombre de véhicules, taux de conformité, trajets publiés, alertes |
| 9.6 | Karim accède au back-office | Refus 403 |

---

## 10. Checklist d'erreurs API (récapitulatif)

| Situation | Code | Corps |
|---|---|---|
| Jeton absent / expiré | 401 | `{"detail": "…"}` |
| PME crée un véhicule, transporteur utilise `/compatibles/` | 403 | `{"detail": "…"}` |
| Véhicule d'un autre transporteur | 404 | `{"detail": "Not found."}` |
| Capacité > véhicule, date passée, immat doublon, document expiré | 422 | `{"erreurs": {"champ": ["message"]}}` |
| Erreur métier (surbooking, publication véhicule bloqué) | 422 | `{"detail": "message en français"}` |

---

## 11. Tests automatisés (rappel)

```bash
pytest apps/fleet                # 50 tests : modèles, services, API, permissions
pytest apps/fleet --cov          # couverture ≈ 81 %
pytest                           # toute la suite (229 tests)
```

**Critère de réussite du scénario** : toutes les étapes ci-dessus passent, en particulier 2.7, 4.4, 6.2-6.3 (blocage automatique) et 8.5 (certificat PDF).
