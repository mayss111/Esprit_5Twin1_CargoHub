import { useEffect, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api, messageErreur } from "./api.js";

export default function ImpactEcolo() {
  const [vehicules, setVehicules] = useState([]);
  const [choisi, setChoisi] = useState("");
  const [bilans, setBilans] = useState({});
  const [erreur, setErreur] = useState("");
  const [message, setMessage] = useState("");

  useEffect(() => {
    api
      .get("/fleet/vehicules/")
      .then((r) => setVehicules(r.data.results || r.data))
      .catch((e) => setErreur(messageErreur(e)));
  }, []);

  useEffect(() => {
    vehicules.forEach((v) => {
      api
        .get(`/fleet/vehicules/${v.id}/impact/`)
        .then((r) => setBilans((anciens) => ({ ...anciens, [v.id]: r.data })))
        .catch(() => { });
    });
  }, [vehicules]);

  const telechargerCertificat = async () => {
    const id = choisi || vehicules[0]?.id;
    if (!id) return;
    try {
      const reponse = await api.get(`/fleet/vehicules/${id}/certificat/`, { responseType: "blob" });
      const lien = URL.createObjectURL(reponse.data);
      const a = document.createElement("a");
      a.href = lien;
      a.download = `certificat-vert-${id}.pdf`;
      a.click();
      URL.revokeObjectURL(lien);
      setMessage("Certificat vert téléchargé.");
    } catch (e) {
      setErreur(messageErreur(e));
    }
  };

  const donneesGraphique = vehicules.map((v) => ({
    nom: v.immatriculation,
    co2: bilans[v.id]?.co2_total_kg || 0,
  }));

  return (
    <>
      <h1 className="ch-titre">Impact écologique</h1>
      <p className="ch-sous-titre">
        CO₂ émis par vos trajets (charge partagée) et points éco gagnés — 1 point tous les 100 kg.
      </p>
      {erreur && <p className="ch-alerte">{erreur}</p>}
      {message && <p className="ch-succes">{message}</p>}

      <div className="ch-grille">
        {vehicules.map((v) => {
          const b = bilans[v.id] || { nb_trajets: 0, co2_total_kg: 0, points_eco: 0 };
          return (
            <div className="ch-carte" key={v.id}>
              <strong>{v.immatriculation}</strong>
              <p style={{ margin: "0.4rem 0 0" }}>
                {b.nb_trajets} trajet(s) · {b.co2_total_kg} kg CO₂ · <span style={{ color: "#2e9e5b" }}>{b.points_eco} pts éco</span>
              </p>
            </div>
          );
        })}
        {vehicules.length === 0 && <div className="ch-carte">Aucun véhicule enregistré.</div>}
      </div>

      {donneesGraphique.length > 0 && (
        <div className="ch-carte">
          <h2 style={{ fontSize: "1.1rem", marginTop: 0 }}>CO₂ par véhicule</h2>
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={donneesGraphique}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="nom" />
              <YAxis unit=" kg" />
              <Tooltip formatter={(valeur) => [`${valeur} kg`, "CO₂"]} />
              <Bar dataKey="co2" fill="#F5A623" radius={[6, 6, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      <div className="ch-carte">
        <h2 style={{ fontSize: "1.1rem", marginTop: 0 }}>Certificat vert</h2>
        <label className="ch-champ" style={{ maxWidth: 320 }}>
          <span>Véhicule</span>
          <select value={choisi} onChange={(e) => setChoisi(e.target.value)}>
            <option value="">Tous (premier véhicule)</option>
            {vehicules.map((v) => (
              <option key={v.id} value={v.id}>{v.immatriculation}</option>
            ))}
          </select>
        </label>
        <br />
        <button className="ch-bouton" onClick={telechargerCertificat}>⬇ Télécharger le certificat (PDF)</button>
      </div>
    </>
  );
}
