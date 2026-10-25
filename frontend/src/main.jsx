import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import Connexion from "./features/fleet/Connexion.jsx";
import ImpactEcolo from "./features/fleet/ImpactEcolo.jsx";
import Entretiens from "./features/fleet/Maintenance.jsx";
import MesTrajets from "./features/fleet/MesTrajets.jsx";
import MaFlotte from "./features/fleet/MaFlotte.jsx";
import Layout from "./Layout.jsx";
import "./styles.css";

ReactDOM.createRoot(document.getElementById("root")).render(
  <BrowserRouter>
    <Routes>
      <Route path="/connexion" element={<Connexion />} />
      <Route element={<Layout />}>
        <Route path="/flotte" element={<MaFlotte />} />
        <Route path="/trajets" element={<MesTrajets />} />
        <Route path="/entretien" element={<Entretiens />} />
        <Route path="/impact" element={<ImpactEcolo />} />
        <Route path="*" element={<Navigate to="/flotte" replace />} />
      </Route>
    </Routes>
  </BrowserRouter>
);
