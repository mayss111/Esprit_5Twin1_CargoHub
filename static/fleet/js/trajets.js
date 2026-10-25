/*
 * M3 — page « Mes trajets ».
 *  - Confirmation avant d'annuler un trajet (<form data-confirmer="…">).
 *  - Carte Leaflet des trajets et calcul d'itinéraires routiers (Valhalla / OpenStreetMap),
 *    à partir des données {{ trajets_carte|json_script:"donnees-trajets" }}.
 */
(() => {
  document.querySelectorAll("form[data-confirmer]").forEach((form) => {
    form.addEventListener("submit", (event) => {
      if (!window.confirm(form.dataset.confirmer)) event.preventDefault();
    });
  });

  const donnees = document.getElementById("donnees-trajets");
  if (!donnees || typeof L === "undefined") return;

  // Centres-villes approximatifs (le modèle ne stocke pas encore de coordonnées).
  const VILLES = {
    tunis: [36.8065, 10.1815], sfax: [34.7406, 10.7603], sousse: [35.8256, 10.6084],
    monastir: [35.778, 10.8262], bizerte: [37.274, 9.8739], gabes: [33.8815, 10.0982],
    nabeul: [36.4561, 10.7376], djerba: [33.8076, 10.8451], kairouan: [35.6781, 10.0963],
    tozeur: [33.9197, 8.1335], gafsa: [34.425, 8.7842], tabarka: [36.9544, 8.7581],
    "el kef": [36.1742, 8.7049], "le kef": [36.1742, 8.7049], kef: [36.1742, 8.7049],
    siliana: [36.0849, 9.3708], beja: [36.7256, 9.1892], jendouba: [36.5011, 8.7803],
    kasserine: [35.1676, 8.8365], "sidi bouzid": [35.0403, 9.4849], mahdia: [35.5047, 11.0622],
    zarzis: [33.5086, 11.0956], medenine: [33.355, 10.5055], tataouine: [33.1412, 10.0503],
    ariana: [36.8625, 10.1956], "ben arous": [36.7533, 10.2281], "la marsa": [36.8783, 10.3247],
    hammamet: [36.4, 10.6167],
  };
  // Minuscules, sans accents, tirets et espaces unifiés : « Béja » → « beja ».
  const cleVille = (nom) =>
    (nom || "").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "")
      .replace(/-/g, " ").replace(/\s+/g, " ").trim();

  const trajets = JSON.parse(donnees.textContent);
  const choix = document.getElementById("choix-itineraires");
  const resultat = document.getElementById("resultat-itineraire");
  const couleurs = ["#F5A623", "#2563EB", "#7C3AED", "#0E9F8E"];
  const cacheRoutes = {};

  const carte = L.map("carte-trajets").setView([34.9, 9.8], 6);
  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
    maxZoom: 19,
  }).addTo(carte);
  const calquesRoutes = L.layerGroup().addTo(carte);

  const alerte = (classe, texte) => {
    const div = document.createElement("div");
    div.className = `alert ${classe}`;
    div.setAttribute("role", "status");
    div.textContent = texte;
    return div;
  };

  const duree = (secondes) => {
    const heures = Math.floor(secondes / 3600);
    const minutes = Math.round((secondes % 3600) / 60);
    return heures ? `${heures} h ${minutes} min` : `${minutes} min`;
  };

  function afficherOptions(trajet, routes) {
    resultat.replaceChildren();
    calquesRoutes.clearLayers();
    const titre = document.createElement("h3");
    titre.className = "h6 mb-3";
    titre.textContent = `Options routières · ${trajet.ville_depart} → ${trajet.ville_arrivee}`;
    resultat.appendChild(titre);

    routes.forEach((route, index) => {
      const couleur = couleurs[index % couleurs.length];
      const ligne = document.createElement("div");
      ligne.className = "card card-ch p-3 mb-2";
      ligne.style.borderLeft = `4px solid ${couleur}`;

      const resume = document.createElement("div");
      resume.className = "d-flex flex-wrap justify-content-between align-items-center gap-2";
      const texte = document.createElement("span");
      texte.textContent = `${index === 0 ? "Meilleur choix" : `Alternative ${index}`} · `
        + `${(route.distance / 1000).toFixed(1)} km · ${duree(route.duration)}`;
      const afficher = document.createElement("button");
      afficher.type = "button";
      afficher.className = `btn btn-sm ${index === 0 ? "btn-accent" : "btn-outline-secondary"}`;
      afficher.textContent = "Afficher sur la carte";
      afficher.setAttribute("aria-label", `Afficher l’itinéraire ${index + 1} sur la carte`);
      afficher.addEventListener("click", () => {
        calquesRoutes.clearLayers();
        const points = route.geometry.coordinates.map(([lon, lat]) => [lat, lon]);
        const trace = L.polyline(points, { color: couleur, weight: index === 0 ? 6 : 5, opacity: 0.9 }).addTo(calquesRoutes);
        carte.fitBounds(trace.getBounds(), { padding: [30, 30] });
      });
      resume.append(texte, afficher);
      ligne.appendChild(resume);

      const instructions = (route.legs || []).flatMap((leg) =>
        (leg.steps || []).map((step) => step.maneuver?.instruction
          || [step.maneuver?.type, step.name].filter(Boolean).join(" · ")).filter(Boolean));
      if (instructions.length) {
        const details = document.createElement("details");
        details.className = "mt-2 small";
        const summary = document.createElement("summary");
        summary.textContent = "Voir les indications de route";
        const liste = document.createElement("ol");
        liste.className = "mt-2 mb-0";
        instructions.forEach((instruction) => {
          const li = document.createElement("li");
          li.textContent = instruction;
          liste.appendChild(li);
        });
        details.append(summary, liste);
        ligne.appendChild(details);
      }
      resultat.appendChild(ligne);
      if (index === 0) afficher.click();
    });
  }

  async function calculerRoute(trajet, depart, arrivee) {
    if (cacheRoutes[trajet.id]) {
      afficherOptions(trajet, cacheRoutes[trajet.id]);
      return;
    }
    resultat.replaceChildren(alerte("alert-info", "Recherche des itinéraires…"));
    const camionnette = trajet.type_vehicule === "CAMIONNETTE";
    const requete = {
      locations: [{ lat: depart[0], lon: depart[1] }, { lat: arrivee[0], lon: arrivee[1] }],
      costing: camionnette ? "auto" : "truck",
      units: "kilometers",
      language: "fr-FR",
      format: "osrm",
      shape_format: "geojson",
      directions_type: "instructions",
      alternates: 2,
    };
    if (!camionnette) requete.costing_options = { truck: { use_truck_route: 0.5 } };
    try {
      const reponse = await fetch("https://valhalla1.openstreetmap.de/route", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Client-Id": "CargoHub" },
        body: JSON.stringify(requete),
        signal: AbortSignal.timeout(15000),
      });
      if (!reponse.ok) throw new Error("service indisponible");
      const json = await reponse.json();
      if (!json.routes?.length) throw new Error("aucun itinéraire");
      // Le premier choix minimise le temps estimé.
      const routes = json.routes.slice().sort((a, b) => a.duration - b.duration || a.distance - b.distance);
      cacheRoutes[trajet.id] = routes;
      afficherOptions(trajet, routes);
    } catch {
      resultat.replaceChildren(alerte(
        "alert-warning", "Impossible de calculer l’itinéraire pour le moment. Vérifiez la connexion puis réessayez."));
    }
  }

  const bornes = [];
  trajets.forEach((trajet) => {
    const depart = VILLES[cleVille(trajet.ville_depart)];
    const arrivee = VILLES[cleVille(trajet.ville_arrivee)];
    [depart, arrivee].filter(Boolean).forEach((point) => {
      L.marker(point).addTo(carte);
      bornes.push(point);
    });
    if (depart && arrivee) {
      const bouton = document.createElement("button");
      bouton.type = "button";
      bouton.className = "btn btn-sm btn-outline-primary me-2 mb-2";
      bouton.textContent = `Itinéraire ${trajet.ville_depart} → ${trajet.ville_arrivee}`;
      bouton.addEventListener("click", () => calculerRoute(trajet, depart, arrivee));
      choix.appendChild(bouton);
    }
  });
  if (bornes.length) carte.fitBounds(bornes, { padding: [30, 30] });
  if (!choix.children.length) choix.textContent = "Les villes de ces trajets ne sont pas encore placées sur la carte.";
  setTimeout(() => carte.invalidateSize(), 150);
})();
