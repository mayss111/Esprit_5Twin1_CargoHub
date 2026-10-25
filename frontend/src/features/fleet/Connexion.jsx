import { useState } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";

export default function Connexion() {
  const [email, setEmail] = useState("karim@transport.tn");
  const [motDePasse, setMotDePasse] = useState("cargohub2026");
  const [erreur, setErreur] = useState("");
  const naviguer = useNavigate();

  const soumettre = async (evenement) => {
    evenement.preventDefault();
    setErreur("");
    try {
      const reponse = await axios.post("/api/token/", { email, password: motDePasse });
      localStorage.setItem("cargohub-jeton", reponse.data.access);
      localStorage.setItem("cargohub-refresh", reponse.data.refresh);
      naviguer("/flotte");
    } catch (e) {
      if (!e.response) setErreur("API injoignable. Lancez Django sur http://localhost:8000.");
      else setErreur("Identifiants incorrects. Réessayez (démo : karim@transport.tn / cargohub2026).");
    }
  };

  return (
    <main className="ch-main" style={{ maxWidth: 420 }}>
      <h1 className="ch-titre">CargoHub — Espace transporteur</h1>
      <p className="ch-sous-titre">Connexion JWT vers l'API Django.</p>
      <form className="ch-carte" onSubmit={soumettre}>
        {erreur && <p className="ch-alerte">{erreur}</p>}
        <label className="ch-champ">
          <span>Email</span>
          <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
        </label>
        <label className="ch-champ">
          <span>Mot de passe</span>
          <input type="password" required value={motDePasse} onChange={(e) => setMotDePasse(e.target.value)} />
        </label>
        <button className="ch-bouton">Se connecter</button>
        <p className="ch-sous-titre" style={{ marginTop: "1rem" }}>
          Démo : karim@transport.tn / cargohub2026
        </p>
      </form>
    </main>
  );
}
