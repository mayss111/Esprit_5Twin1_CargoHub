import { useEffect, useMemo, useRef, useState } from "react";
import L from "leaflet";
import iconUrl from "leaflet/dist/images/marker-icon.png";
import iconRetinaUrl from "leaflet/dist/images/marker-icon-2x.png";
import shadowUrl from "leaflet/dist/images/marker-shadow.png";
import "leaflet/dist/leaflet.css";
import { api, messageErreur } from "./api.js";

// Libellés des statuts du modèle Trajet (apps/fleet/models.py).
const STATUTS_TRAJET = {
  OUVERT: "Ouvert aux réservations",
  COMPLET: "Complet",
  EN_COURS: "En cours",
  TERMINE: "Terminé",
  ANNULE: "Annulé",
};

delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({ iconUrl, iconRetinaUrl, shadowUrl });

// Coordonnées approximatives des grandes villes tunisiennes.
const VILLES = {
  tunis: [36.8065, 10.1815],
  sfax: [34.7406, 10.7603],
  sousse: [35.8256, 10.6084],
  monastir: [35.778, 10.8262],
  bizerte: [37.274, 9.8739],
  gabes: [33.8815, 10.0982],
  nabeul: [36.4561, 10.7376],
  djerba: [33.8076, 10.8451],
  kairouan: [35.6781, 10.0963],
  tozeur: [33.9197, 8.1335],
  gafsa: [34.425, 8.7842],
  hammamet: [36.4, 10.6167],
  ariana: [36.8625, 10.1956],
  "ben arous": [36.7533, 10.2281],
  mahdia: [35.5047, 11.0622],
};

function cleVille(nom) {
  return (nom || "")
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/-/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

export default function MesTrajets() {
  const [trajets, setTrajets] = useState([]);
  const [vehicules, setVehicules] = useState([]);
  const [erreur, setErreur] = useState("");
  const [message, setMessage] = useState("");
  const [formulaireOuvert, setFormulaireOuvert] = useState(false);

  const charger = async () => {
    try {
      const [t, v] = await Promise.all([api.get("/fleet/trajets/"), api.get("/fleet/vehicules/")]);
      setTrajets(t.data.results || t.data);
      setVehicules((v.data.results || v.data).filter((x) => x.statut === "ACTIF"));
    } catch (e) {
      setErreur(messageErreur(e));
    }
  };

  useEffect(() => {
    charger();
  }, []);

  const publier = async (donnees) => {
    try {
      await api.post("/fleet/trajets/", donnees);
      setMessage("Trajet publié.");
      setFormulaireOuvert(false);
      charger();
    } catch (e) {
      throw new Error(messageErreur(e));
    }
  };

  const annuler = async (id) => {
    try {
      await api.delete(`/fleet/trajets/${id}/`);
      charger();
    } catch (e) {
      setErreur(messageErreur(e));
    }
  };

  return (
    <>
      <h1 className="ch-titre">Mes trajets</h1>
      <p className="ch-sous-titre">Publiez vos trajets et suivez leur remplissage.</p>
      {erreur && <p className="ch-alerte">{erreur}</p>}
      {message && <p className="ch-succes">{message}</p>}

      {!formulaireOuvert && (
        <button className="ch-bouton" onClick={() => setFormulaireOuvert(true)}>+ Publier un trajet</button>
      )}
      {formulaireOuvert && (
        <FormulaireTrajet
          vehicules={vehicules}
          onAnnuler={() => setFormulaireOuvert(false)}
          onPublier={publier}
        />
      )}

      <div className="ch-carte" style={{ overflowX: "auto" }}>
        <table className="ch-tableau">
          <thead>
            <tr>
              <th>Trajet</th>
              <th>Départ</th>
              <th>Véhicule</th>
              <th>Place libre</th>
              <th>Remplissage</th>
              <th>Statut</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {trajets.map((t) => (
              <tr key={t.id}>
                <td>
                  <strong>{t.ville_depart} → {t.ville_arrivee}</strong>
                  {t.etapes?.length > 0 && <div style={{ fontSize: "0.85em" }}>via {t.etapes.join(", ")}</div>}
                </td>
                <td>{new Date(t.date_depart).toLocaleString("fr-TN")}</td>
                <td>{t.vehicule_immatriculation}</td>
                <td>{t.capacite_dispo_kg} kg · {t.capacite_dispo_m3} m³</td>
                <td>{Math.round((t.taux_remplissage || 0) * 100)} %</td>
                <td>{STATUTS_TRAJET[t.statut] || t.statut}</td>
                <td>
                  {(t.statut === "OUVERT" || t.statut === "COMPLET") && (
                    <button className="ch-bouton secondaire" style={{ padding: "0.3rem 0.7rem" }} onClick={() => annuler(t.id)}>
                      Annuler
                    </button>
                  )}
                </td>
              </tr>
            ))}
            {trajets.length === 0 && (
              <tr><td colSpan="7">Aucun trajet publié.</td></tr>
            )}
          </tbody>
        </table>
      </div>

      <CarteTrajets trajets={trajets} />
    </>
  );
}

function FormulaireTrajet({ vehicules, onPublier, onAnnuler }) {
  const [donnees, setDonnees] = useState({
    vehicule: "",
    ville_depart: "",
    ville_arrivee: "",
    date_depart: "",
    capacite_dispo_kg: "",
    capacite_dispo_m3: "",
    distance_km: "",
    prix_indicatif: "",
  });
  const [erreurs, setErreurs] = useState({});

  const vehiculeChoisi = useMemo(
    () => vehicules.find((v) => String(v.id) === String(donnees.vehicule)),
    [vehicules, donnees.vehicule]
  );

  const valider = () => {
    const e = {};
    if (!donnees.vehicule) e.vehicule = "Choisissez un véhicule.";
    if (!donnees.ville_depart.trim()) e.ville_depart = "Ville de départ obligatoire.";
    if (!donnees.ville_arrivee.trim()) e.ville_arrivee = "Ville d'arrivée obligatoire.";
    if (donnees.ville_depart.trim().toLowerCase() === donnees.ville_arrivee.trim().toLowerCase())
      e.ville_arrivee = "Les deux villes doivent être différentes.";
    if (!donnees.date_depart || new Date(donnees.date_depart) <= new Date())
      e.date_depart = "La date de départ doit être dans le futur.";
    if (!donnees.capacite_dispo_kg || Number(donnees.capacite_dispo_kg) <= 0)
      e.capacite_dispo_kg = "Capacité (kg) requise.";
    if (vehiculeChoisi && Number(donnees.capacite_dispo_kg) > vehiculeChoisi.capacite_kg)
      e.capacite_dispo_kg = `Maximum : ${vehiculeChoisi.capacite_kg} kg.`;
    if (!donnees.capacite_dispo_m3 || Number(donnees.capacite_dispo_m3) <= 0)
      e.capacite_dispo_m3 = "Capacité (m³) requise.";
    if (vehiculeChoisi && Number(donnees.capacite_dispo_m3) > vehiculeChoisi.capacite_m3)
      e.capacite_dispo_m3 = `Maximum : ${vehiculeChoisi.capacite_m3} m³.`;
    if (donnees.distance_km && Number(donnees.distance_km) <= 0)
      e.distance_km = "La distance doit être supérieure à 0.";
    return e;
  };

  const soumettre = async (evenement) => {
    evenement.preventDefault();
    const e = valider();
    setErreurs(e);
    if (Object.keys(e).length) return;
    try {
      await onPublier({
        ...donnees,
        capacite_dispo_kg: Number(donnees.capacite_dispo_kg),
        capacite_dispo_m3: Number(donnees.capacite_dispo_m3),
        date_depart: new Date(donnees.date_depart).toISOString(),
        distance_km: donnees.distance_km ? Number(donnees.distance_km) : null,
        prix_indicatif: donnees.prix_indicatif ? Number(donnees.prix_indicatif) : null,
      });
    } catch (erreurPublication) {
      setErreurs({ global: erreurPublication.message });
    }
  };

  return (
    <form className="ch-carte" onSubmit={soumettre}>
      {erreurs.global && <p className="ch-alerte">{erreurs.global}</p>}
      <div className="ch-grille">
        <label className="ch-champ">
          <span>Véhicule</span>
          <select value={donnees.vehicule} onChange={(e) => setDonnees({ ...donnees, vehicule: e.target.value })}>
            <option value="">— choisir —</option>
            {vehicules.map((v) => (
              <option key={v.id} value={v.id}>
                {v.immatriculation} ({v.capacite_kg} kg)
              </option>
            ))}
          </select>
          {erreurs.vehicule && <p className="ch-erreur">{erreurs.vehicule}</p>}
        </label>
        <label className="ch-champ">
          <span>Ville de départ</span>
          <input list="villes" value={donnees.ville_depart} onChange={(e) => setDonnees({ ...donnees, ville_depart: e.target.value })} />
          <datalist id="villes">{Object.keys(VILLES).map((v) => <option key={v} value={v} />)}</datalist>
          {erreurs.ville_depart && <p className="ch-erreur">{erreurs.ville_depart}</p>}
        </label>
        <label className="ch-champ">
          <span>Ville d'arrivée</span>
          <input list="villes" value={donnees.ville_arrivee} onChange={(e) => setDonnees({ ...donnees, ville_arrivee: e.target.value })} />
          {erreurs.ville_arrivee && <p className="ch-erreur">{erreurs.ville_arrivee}</p>}
        </label>
        <label className="ch-champ">
          <span>Date et heure de départ</span>
          <input type="datetime-local" value={donnees.date_depart} onChange={(e) => setDonnees({ ...donnees, date_depart: e.target.value })} />
          {erreurs.date_depart && <p className="ch-erreur">{erreurs.date_depart}</p>}
        </label>
        <label className="ch-champ">
          <span>Capacité disponible (kg)</span>
          <input type="number" min="1" value={donnees.capacite_dispo_kg} onChange={(e) => setDonnees({ ...donnees, capacite_dispo_kg: e.target.value })} />
          {erreurs.capacite_dispo_kg && <p className="ch-erreur">{erreurs.capacite_dispo_kg}</p>}
        </label>
        <label className="ch-champ">
          <span>Capacité disponible (m³)</span>
          <input type="number" step="0.01" min="0.01" value={donnees.capacite_dispo_m3} onChange={(e) => setDonnees({ ...donnees, capacite_dispo_m3: e.target.value })} />
          {erreurs.capacite_dispo_m3 && <p className="ch-erreur">{erreurs.capacite_dispo_m3}</p>}
        </label>
        <label className="ch-champ">
          <span>Distance (km) — CO₂ et suggestion de prix des appels d'offres</span>
          <input type="number" min="1" value={donnees.distance_km} onChange={(e) => setDonnees({ ...donnees, distance_km: e.target.value })} />
          {erreurs.distance_km && <p className="ch-erreur">{erreurs.distance_km}</p>}
        </label>
        <label className="ch-champ">
          <span>Prix indicatif (DT, optionnel)</span>
          <input type="number" step="0.5" value={donnees.prix_indicatif} onChange={(e) => setDonnees({ ...donnees, prix_indicatif: e.target.value })} />
        </label>
      </div>
      <button className="ch-bouton">Publier</button>{" "}
      <button type="button" className="ch-bouton secondaire" onClick={onAnnuler}>Annuler</button>
    </form>
  );
}

function CarteTrajets({ trajets }) {
  const conteneur = useRef(null);
  const carteRef = useRef(null);
  const [pret, setPret] = useState(false);

  useEffect(() => {
    if (!conteneur.current) return undefined;
    const instance = L.map(conteneur.current).setView([34.9, 9.8], 6);
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
      maxZoom: 19,
      // Les tuiles OSM exigent un en-tête Referer, sinon elles répondent 403.
      referrerPolicy: "strict-origin-when-cross-origin",
    }).addTo(instance);
    carteRef.current = instance;
    const timer = setTimeout(() => instance.invalidateSize(), 150);
    setPret(true);
    return () => {
      clearTimeout(timer);
      instance.remove();
      carteRef.current = null;
      setPret(false);
    };
  }, []);

  useEffect(() => {
    const carte = carteRef.current;
    if (!carte || !pret) return;
    carte.eachLayer((couche) => {
      if (couche instanceof L.Marker || couche instanceof L.Polyline) couche.remove();
    });
    let aMarque = false;
    trajets.forEach((t) => {
      const depart = VILLES[cleVille(t.ville_depart)];
      const arrivee = VILLES[cleVille(t.ville_arrivee)];
      if (depart) {
        L.marker(depart).addTo(carte).bindPopup(`Départ : ${t.ville_depart}`);
        aMarque = true;
      }
      if (arrivee) {
        L.marker(arrivee).addTo(carte).bindPopup(`Arrivée : ${t.ville_arrivee}`);
        aMarque = true;
      }
      if (depart && arrivee)
        L.polyline([depart, arrivee], { color: "#F5A623", weight: 3 })
          .addTo(carte)
          .bindPopup(`${t.ville_depart} → ${t.ville_arrivee}`);
    });
    if (aMarque) carte.fitBounds(carte.getBounds(), { padding: [30, 30] });
    setTimeout(() => carte.invalidateSize(), 80);
  }, [pret, trajets]);

  return (
    <div>
      <h2 style={{ fontSize: "1.1rem" }}>Vos trajets sur la carte</h2>
      <div ref={conteneur} id="carte-trajets" className="ch-carte-map" />
    </div>
  );
}
