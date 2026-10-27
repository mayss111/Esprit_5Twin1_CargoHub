# Scénario de test manuel — Module 3 « Flotte & trajets »

Objectif : parcourir toutes les fonctionnalités du module (flotte, documents, conformité, trajets,
CO₂, planificateur IA, back-office) comme un utilisateur réel, et vérifier les règles métier.
Les tests automatiques correspondants sont dans `apps/fleet/tests.py` (`pytest apps/fleet`).

## 0. Préparation

```bash
docker compose up --build -d      # ou : python manage.py runserver
python manage.py migrate
python manage.py donnees_demo     # comptes + données de démonstration
python manage.py donnees_demo_co2 # trajets terminés + livraison pour tester les bilans
python manage.py donnees_demo_co2 # trajets terminés + livraison pour les rapports CO₂
```

Comptes de démo (mot de passe : `cargohub2026`) :

| Rôle | Email | Utilisation |
|---|---|---|
| ADMIN | `admin@cargohub.tn` | back-office |
| TRANSPORTEUR | `karim@transport.tn` | espace flotte |
| PME | `sami@atelier.tn` | réservations, appels d'offres |

## 1. Accès

| # | Action | Résultat attendu |
|---|---|---|
| 1.1 | Ouvrir `/flotte/vehicules/` sans être connecté | Redirection vers la connexion |
| 1.2 | Connecté en PME, ouvrir `/flotte/vehicules/` | 403 : la flotte est réservée aux transporteurs |
| 1.3 | Connecté en Karim, ouvrir le véhicule d'un autre transporteur (`/flotte/vehicules/<id>/modifier/`) | 404 |

## 2. Véhicules et documents (Mes véhicules)

| # | Action | Résultat attendu |
|---|---|---|
| 2.1 | Ajouter un camion `999 tu 1111`, 3000 kg, 20 m³ | Créé, immatriculation en majuscules, statut **Actif** |
| 2.2 | Ajouter un véhicule avec une immatriculation existante | Erreur sur le champ |
| 2.3 | Envoyer une assurance PDF qui expire dans 6 mois | Badge « Assurance · date », conformité inchangée |
| 2.4 | Renvoyer une assurance | Remplace l'ancienne (un seul document par type) |
| 2.5 | Envoyer un `.txt` renommé en `.pdf`, ou un fichier de plus de 5 Mo | Message d'erreur, rien n'est enregistré |
| 2.6 | Réduire la capacité sous la place proposée d'un trajet actif | Erreur sur le champ |
| 2.7 | Supprimer un véhicule qui a des trajets | Refusé avec un message ; sans trajet : supprimé |
| 2.8 | Télécharger le **certificat vert** | PDF du véhicule pour l'année en cours |

## 3. Conformité (tâches Celery quotidiennes)

| # | Action | Résultat attendu |
|---|---|---|
| 3.1 | Dans l'admin Django, passer la date d'expiration d'un document à hier puis lancer `apps.maintenance.tasks.verifier_conformite` | Véhicule **Non conforme** + motif, notification au transporteur |
| 3.2 | Publier un trajet avec ce véhicule | Il n'est pas proposé dans la liste des véhicules |
| 3.3 | Renouveler le document puis relancer la tâche | Véhicule de nouveau **Actif**, notification |
| 3.4 | Document qui expire dans moins de 30 jours, lancer `apps.fleet.tasks.notifier_alerte_documents` | Notification + email « Document bientôt expiré » |

## 4. Trajets (Mes trajets)

| # | Action | Résultat attendu |
|---|---|---|
| 4.1 | Publier Sousse → Tunis via Hammamet, demain 08:00, 1500 kg, 10 m³, 140 km, 90 DT | Statut **Ouvert aux réservations**, étape affichée |
| 4.2 | Date passée, place supérieure au véhicule, départ = arrivée, distance vide | Erreur sur le champ concerné |
| 4.3 | Côté PME : « Trouver un camion » pour une expédition Sousse → Tunis à ± 2 jours | Le trajet est proposé (module Réservations) |
| 4.4 | Accepter la réservation, puis réduire la place proposée sous la part réservée | Refusé ; la colonne « Remplissage » reflète la part réservée |
| 4.5 | Annuler un trajet avec une réservation acceptée | Refusé ; sans réservation : statut **Annulé**, plus modifiable |
| 4.6 | Carte : cliquer « Itinéraire Sousse → Tunis » | Jusqu'à 3 itinéraires, le plus rapide en premier |

## 5. Impact écologique et planificateur IA

| # | Action | Résultat attendu |
|---|---|---|
| 5.1 | Ouvrir **Impact écologique** depuis le menu transporteur | Total de la flotte, graphique et bilan par véhicule (trajets terminés, CO₂, points éco) |
| 5.2 | Ouvrir **CO₂ économisé** après une réservation livrée | Rapport partagé contre transport dédié, visible sur `/ecologie/` |
| 5.3 | **Planificateur IA** : Sousse → Tunis, 2000 kg, 10 m³, 140 km | Véhicules classés (capacité 55 %, CO₂ 25 %, entretien 20 %) |
| 5.4 | Même mission avec un poids supérieur à tous les véhicules | Message « Aucun véhicule actif et conforme… » |

## 6. Back-office (admin)

| # | Action | Résultat attendu |
|---|---|---|
| 6.1 | Menu M3 → **Véhicules** | Indicateurs (véhicules, non conformes, trajets ouverts), filtre par statut, documents consultables |
| 6.2 | Refuser un véhicule avec un motif | **Non conforme** + motif ; il ne peut plus publier de trajet |
| 6.3 | Valider ce véhicule | De nouveau **Actif** |
| 6.4 | Menu M3 → **Trajets** | Tous les trajets de tous les transporteurs |
| 6.5 | Facteurs CO₂ par type de véhicule | Modifiables dans l'admin Django (`FacteurEmission`) |

## 7. API REST (JWT)

L'interface web est rendue par Django sur `http://localhost:8000`.
Détail des routes : `apps/fleet/README.md`. Tests automatiques : `apps/fleet/tests_api.py`.

```bash
# Jeton (sans jeton : 401)
curl -X POST http://localhost:8000/api/token/ -H "Content-Type: application/json" \
  -d '{"email": "karim@transport.tn", "password": "cargohub2026"}'

# Publier un trajet (place libre = place proposée à la création)
curl -X POST http://localhost:8000/api/fleet/trajets/ -H "Authorization: Bearer <ACCESS>" \
  -H "Content-Type: application/json" \
  -d '{"vehicule": 1, "ville_depart": "Sousse", "ville_arrivee": "Tunis", "date_depart": "2026-11-02T08:00:00Z",
       "capacite_dispo_kg": "1500", "capacite_dispo_m3": "10", "distance_km": 140, "prix_indicatif": "90"}'

# Recherche de trajets ouverts (jeton PME ; transporteur → 403)
curl "http://localhost:8000/api/fleet/trajets/compatibles/?ville_depart=Sousse&ville_arrivee=Tunis&poids_kg=250" \
  -H "Authorization: Bearer <JETON_PME>"
```

| # | Action | Résultat attendu |
|---|---|---|
| 7.1 | Créer un trajet via l'API | Statut `OUVERT`, visible dans « Mes trajets » |
| 7.2 | Capacité supérieure au véhicule, date passée, véhicule d'un autre transporteur | 422 / 422 / 403 |
| 7.3 | Après une réservation acceptée, `PATCH` avec `capacite_totale_kg` sous la part réservée | 422 |
| 7.4 | `DELETE` d'un trajet qui a une réservation acceptée | 422 ; sans réservation : 204, statut `ANNULE` |
| 7.5 | `PATCH /api/fleet/vehicules/{id}/statut/` (admin) | Statut changé ; transporteur → 403 |
| 7.6 | `GET /api/fleet/vehicules/{id}/impact/?debut=2026-01-01` puis `…/certificat/` | Bilan CO₂ du véhicule, puis PDF |
