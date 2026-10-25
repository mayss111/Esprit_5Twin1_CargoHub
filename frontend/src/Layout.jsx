import { useEffect } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";

const LIENS = [
  ["/flotte", "Ma flotte"],
  ["/trajets", "Mes trajets"],
  ["/entretien", "Maintenance"],
  ["/impact", "Impact écologique"],
];

export default function Layout() {
  const naviguer = useNavigate();

  useEffect(() => {
    if (!localStorage.getItem("cargohub-jeton")) naviguer("/connexion");
  }, [naviguer]);

  const deconnexion = () => {
    localStorage.removeItem("cargohub-jeton");
    localStorage.removeItem("cargohub-refresh");
    naviguer("/connexion");
  };
  return (
    <>
      <header className="ch-header">
        <span className="logo">🚚 CargoHub</span>
        <nav>
          {LIENS.map(([vers, libelle]) => (
            <NavLink key={vers} to={vers} className={({ isActive }) => (isActive ? "actif" : "")}>
              {libelle}
            </NavLink>
          ))}
        </nav>
        <button className="ch-bouton secondaire" style={{ marginLeft: "auto" }} onClick={deconnexion}>
          Déconnexion
        </button>
      </header>
      <main className="ch-main">
        <Outlet />
      </main>
    </>
  );
}
