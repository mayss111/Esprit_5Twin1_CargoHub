import axios from "axios";

// Client API : JWT dans localStorage, erreurs en français, proxy Vite → Django :8000.
export const api = axios.create({ baseURL: "/api" });

api.interceptors.request.use((config) => {
  const jeton = localStorage.getItem("cargohub-jeton");
  if (jeton) config.headers.Authorization = `Bearer ${jeton}`;
  return config;
});

api.interceptors.response.use(
  (reponse) => reponse,
  async (erreur) => {
    const { response, config } = erreur;
    if (response?.status === 401 && !config?._retry && localStorage.getItem("cargohub-refresh")) {
      config._retry = true;
      try {
        const rafraichi = await axios.post("/api/token/refresh/", {
          refresh: localStorage.getItem("cargohub-refresh"),
        });
        localStorage.setItem("cargohub-jeton", rafraichi.data.access);
        config.headers.Authorization = `Bearer ${rafraichi.data.access}`;
        return api(config);
      } catch {
        localStorage.removeItem("cargohub-jeton");
        localStorage.removeItem("cargohub-refresh");
        window.location.href = "/connexion";
      }
    }
    if (response?.status === 401) {
      localStorage.removeItem("cargohub-jeton");
      localStorage.removeItem("cargohub-refresh");
      if (window.location.pathname !== "/connexion") window.location.href = "/connexion";
    }
    return Promise.reject(erreur);
  }
);

/** Extrait un message d'erreur lisible (champs ou détail) d'une réponse DRF. */
export function messageErreur(erreur) {
  const data = erreur.response?.data;
  if (!data) return "Erreur réseau : l'API Django n'est pas joignable (port 8000).";
  if (erreur.response?.status === 401) return "Session expirée. Reconnectez-vous.";
  if (erreur.response?.status === 403) return data.detail || "Accès refusé pour ce rôle.";
  if (data.detail) return data.detail;
  if (data.erreurs)
    return Object.entries(data.erreurs)
      .map(([champ, messages]) => `${champ} : ${[].concat(messages).join(", ")}`)
      .join(" · ");
  return Object.entries(data)
    .map(([champ, messages]) => `${champ} : ${[].concat(messages).join(", ")}`)
    .join(" · ");
}
