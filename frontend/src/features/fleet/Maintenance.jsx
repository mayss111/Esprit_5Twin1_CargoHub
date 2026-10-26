import { useEffect, useState } from "react";
import { api, messageErreur } from "./api.js";

export default function Maintenance() {
  const [entretiens, setEntretiens] = useState([]);
  const [vehicules, setVehicules] = useState([]);
  const [erreur, setErreur] = useState("");
  const [message, setMessage] = useState("");

  const charger = async () => {
    try {
      const [e, v] = await Promise.all([api.get("/fleet/entretiens/"), api.get("/fleet/vehicules/")]);
      setEntretiens(e.data.results || e.data);
      setVehicules(v.data.results || v.data);
    } catch (e) {
      setErreur(messageErreur(e));
    }
  };

  useEffect(() => {
    charger();
  }, []);

  const enregistrer = async (evenement) => {
    evenement.preventDefault();
    const f = new FormData(evenement.target);
    const donnees = Object.fromEntries(f.entries());
    try {
      await api.post("/fleet/entretiens/", {
        ...donnees,
        vehicule: Number(donnees.vehicule),
        kilometrage: Number(donnees.kilometrage),
        cout: Number(donnees.cout || 0),
      });
      setMessage("Entretien enregistré.");
      evenement.target.reset();
      charger();
    } catch (e) {
      setErreur(messageErreur(e));
    }
  };

  return (
    <>
      <h1 className="ch-titre">Maintenance</h1>
      <p className="ch-sous-titre">Suivi des entretiens et rappels automatiques (email + notification à échéance).</p>
      {erreur && <p className="ch-alerte">{erreur}</p>}
      {message && <p className="ch-succes">{message}</p>}

      <form className="ch-carte" onSubmit={enregistrer}>
        <div className="ch-grille">
          <label className="ch-champ">
            <span>Véhicule</span>
            <select name="vehicule" required>
              <option value="">— choisir —</option>
              {vehicules.map((v) => (
                <option key={v.id} value={v.id}>{v.immatriculation}</option>
              ))}
            </select>
          </label>
          <label className="ch-champ">
            <span>Type d'intervention</span>
            <input name="type" required placeholder="Vidange, pneus, freins…" />
          </label>
          <label className="ch-champ">
            <span>Date</span>
            <input type="date" name="date" required />
          </label>
          <label className="ch-champ">
            <span>Kilométrage</span>
            <input type="number" name="kilometrage" min="0" required />
          </label>
          <label className="ch-champ">
            <span>Coût (DT)</span>
            <input type="number" step="0.5" name="cout" min="0" />
          </label>
          <label className="ch-champ">
            <span>Prochaine échéance</span>
            <input type="date" name="prochaine_echeance" />
          </label>
        </div>
        <button className="ch-bouton">Enregistrer l'entretien</button>
      </form>

      <div className="ch-carte" style={{ overflowX: "auto" }}>
        <table className="ch-tableau">
          <thead>
            <tr>
              <th>Véhicule</th>
              <th>Intervention</th>
              <th>Date</th>
              <th>Km</th>
              <th>Coût</th>
              <th>Prochaine échéance</th>
            </tr>
          </thead>
          <tbody>
            {entretiens.map((e) => (
              <tr key={e.id}>
                <td>{e.vehicule_immatriculation || e.vehicule}</td>
                <td>{e.type}</td>
                <td>{e.date}</td>
                <td>{e.kilometrage}</td>
                <td>{e.cout} DT</td>
                <td>{e.prochaine_echeance || "—"}</td>
              </tr>
            ))}
            {entretiens.length === 0 && (
              <tr><td colSpan="6">Aucun entretien enregistré.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </>
  );
}
