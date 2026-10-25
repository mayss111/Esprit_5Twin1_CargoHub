import { useEffect, useState } from "react";
import { api, messageErreur } from "./api.js";

const TYPES = ["CAMIONNETTE", "CAMION", "SEMI_REMORQUE", "FRIGORIFIQUE"];
const BADGE = { ACTIF: "vert", EN_MAINTENANCE: "orange", NON_CONFORME: "rouge" };

export default function MaFlotte() {
  const [vehicules, setVehicules] = useState([]);
  const [erreur, setErreur] = useState("");
  const [message, setMessage] = useState("");
  const [formulaire, setFormulaire] = useState(null); // null = formulaire fermé
  const [erreursChamps, setErreursChamps] = useState({});

  const charger = async () => {
    try {
      const reponse = await api.get("/fleet/vehicules/");
      setVehicules(reponse.data.results || reponse.data);
    } catch (e) {
      setErreur(messageErreur(e));
    }
  };

  useEffect(() => {
    charger();
  }, []);

  const validerLocalement = (donnees) => {
    const erreurs = {};
    if (!donnees.immatriculation.trim()) erreurs.immatriculation = "L'immatriculation est obligatoire.";
    if (!donnees.capacite_kg || Number(donnees.capacite_kg) < 1)
      erreurs.capacite_kg = "La capacité doit être d'au moins 1 kg.";
    if (!donnees.capacite_m3 || Number(donnees.capacite_m3) <= 0) erreurs.capacite_m3 = "Capacité en m³ requise.";
    return erreurs;
  };

  const enregistrer = async (evenement) => {
    evenement.preventDefault();
    setErreur("");
    setErreursChamps({});
    const donnees = formulaire;
    const erreurs = validerLocalement(donnees);
    if (Object.keys(erreurs).length) return setErreursChamps(erreurs);
    try {
      await api.post("/fleet/vehicules/", {
        type: donnees.type,
        immatriculation: donnees.immatriculation.toUpperCase(),
        capacite_kg: Number(donnees.capacite_kg),
        capacite_m3: Number(donnees.capacite_m3),
      });
      setFormulaire(null);
      setMessage("Véhicule ajouté. Il est en attente de validation des documents par l'administrateur.");
      charger();
    } catch (e) {
      setErreur(messageErreur(e));
    }
  };

  const televerserDocument = async (vehicule, type, fichier, expiration) => {
    const charge = new FormData();
    charge.append("type", type);
    charge.append("fichier", fichier);
    charge.append("date_expiration", expiration);
    try {
      await api.post(`/fleet/vehicules/${vehicule.id}/documents/`, charge);
      setMessage("Document enregistré.");
      charger();
    } catch (e) {
      setErreur(messageErreur(e));
    }
  };

  return (
    <>
      <h1 className="ch-titre">Ma flotte</h1>
      <p className="ch-sous-titre">Vos véhicules, leurs documents et leur conformité.</p>
      {erreur && <p className="ch-alerte">{erreur}</p>}
      {message && <p className="ch-succes">{message}</p>}

      {!formulaire && (
        <button className="ch-bouton" onClick={() => setFormulaire({ type: "CAMION", immatriculation: "", capacite_kg: "", capacite_m3: "" })}>
          + Ajouter un véhicule
        </button>
      )}

      {formulaire && (
        <form className="ch-carte" onSubmit={enregistrer}>
          <div className="ch-grille">
            <label className="ch-champ">
              <span>Type</span>
              <select value={formulaire.type} onChange={(e) => setFormulaire({ ...formulaire, type: e.target.value })}>
                {TYPES.map((t) => (
                  <option key={t} value={t}>{t}</option>
                ))}
              </select>
            </label>
            <label className="ch-champ">
              <span>Immatriculation</span>
              <input
                value={formulaire.immatriculation}
                onChange={(e) => setFormulaire({ ...formulaire, immatriculation: e.target.value })}
                placeholder="123 TU 4567"
              />
              {erreursChamps.immatriculation && <p className="ch-erreur">{erreursChamps.immatriculation}</p>}
            </label>
            <label className="ch-champ">
              <span>Capacité (kg)</span>
              <input type="number" min="1" value={formulaire.capacite_kg} onChange={(e) => setFormulaire({ ...formulaire, capacite_kg: e.target.value })} />
              {erreursChamps.capacite_kg && <p className="ch-erreur">{erreursChamps.capacite_kg}</p>}
            </label>
            <label className="ch-champ">
              <span>Capacité (m³)</span>
              <input type="number" step="0.01" min="0.01" value={formulaire.capacite_m3} onChange={(e) => setFormulaire({ ...formulaire, capacite_m3: e.target.value })} />
              {erreursChamps.capacite_m3 && <p className="ch-erreur">{erreursChamps.capacite_m3}</p>}
            </label>
          </div>
          <button className="ch-bouton">Enregistrer</button>{" "}
          <button type="button" className="ch-bouton secondaire" onClick={() => setFormulaire(null)}>
            Annuler
          </button>
        </form>
      )}

      <div className="ch-carte" style={{ overflowX: "auto" }}>
        <table className="ch-tableau">
          <thead>
            <tr>
              <th>Immatriculation</th>
              <th>Type</th>
              <th>Capacité</th>
              <th>Statut</th>
              <th>Documents</th>
            </tr>
          </thead>
          <tbody>
            {vehicules.map((v) => (
              <tr key={v.id}>
                <td><strong>{v.immatriculation}</strong></td>
                <td>{v.type}</td>
                <td>{v.capacite_kg} kg · {v.capacite_m3} m³</td>
                <td>
                  <span className={`ch-badge ${BADGE[v.statut] || "orange"}`}>{v.statut}</span>
                  {v.motif_non_conformite && <div className="ch-erreur">{v.motif_non_conformite}</div>}
                </td>
                <td>
                  <DocumentForm vehicule={v} onUpload={televerserDocument} />
                </td>
              </tr>
            ))}
            {vehicules.length === 0 && (
              <tr>
                <td colSpan="5">Aucun véhicule pour le moment.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </>
  );
}

function DocumentForm({ vehicule, onUpload }) {
  const [type, setType] = useState("CARTE_GRISE");
  const [expiration, setExpiration] = useState("");
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        const fichier = e.target.fichier.files[0];
        if (!fichier || !expiration) return;
        onUpload(vehicule, type, fichier, expiration);
      }}
      style={{ display: "flex", gap: "0.4rem", flexWrap: "wrap", alignItems: "center" }}
    >
      <select value={type} onChange={(e) => setType(e.target.value)}>
        <option value="CARTE_GRISE">Carte grise</option>
        <option value="ASSURANCE">Assurance</option>
      </select>
      <input type="date" value={expiration} onChange={(e) => setExpiration(e.target.value)} required />
      <input type="file" name="fichier" accept=".pdf,image/jpeg,image/png" required />
      <button className="ch-bouton secondaire" style={{ padding: "0.3rem 0.7rem" }}>Envoyer</button>
    </form>
  );
}
