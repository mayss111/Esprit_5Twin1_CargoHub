(function () {
  const zone = document.getElementById("carte-relais");
  const source = document.getElementById("marqueurs-entrepots");
  const points = source ? JSON.parse(source.textContent) : [];
  if (zone && typeof L !== "undefined") {
    const carte = L.map(zone, { scrollWheelZoom: false });
    // Django envoie Referrer-Policy: same-origin. OSM refuse alors les tuiles
    // (image « Access blocked »). Le Referer est limité à l'origine, tuile par tuile.
    const TuileOSM = L.TileLayer.extend({
      createTile: function (coords, done) {
        const tile = document.createElement("img");
        L.DomEvent.on(tile, "load", L.Util.bind(this._tileOnLoad, this, done, tile));
        L.DomEvent.on(tile, "error", L.Util.bind(this._tileOnError, this, done, tile));
        tile.alt = "";
        tile.setAttribute("role", "presentation");
        tile.referrerPolicy = "origin";
        tile.src = this.getTileUrl(coords);
        return tile;
      },
    });
    new TuileOSM("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
    }).addTo(carte);
    const groupe = L.featureGroup();
    points.forEach(function (point) {
      const marqueur = L.circleMarker([point.lat, point.lng], {
        radius: 9,
        color: "#E87722",
        weight: 2,
        fillColor: "#0F1E3D",
        fillOpacity: 0.9,
      });
      marqueur.bindPopup(popup(point));
      marqueur.addTo(groupe);
    });
    groupe.addTo(carte);
    const sourceReco = document.getElementById("recommandations-entrepots");
    const recommandations = sourceReco ? JSON.parse(sourceReco.textContent) : [];
    const retenus = L.featureGroup();
    recommandations.forEach(function (point) {
      if (point.lat == null || point.lng == null) return;
      const marqueur = L.circleMarker([point.lat, point.lng], {
        radius: 13,
        color: "#F59E0B",
        weight: 3,
        fillColor: "#F59E0B",
        fillOpacity: 0.95,
      });
      marqueur.bindPopup(popupRecommandation(point));
      marqueur.addTo(retenus);
    });
    retenus.addTo(carte);
    if (retenus.getLayers().length) {
      carte.fitBounds(retenus.getBounds(), { padding: [28, 28] });
    } else if (points.length === 1) {
      carte.setView([points[0].lat, points[0].lng], 13);
    } else if (points.length > 1) {
      carte.fitBounds(groupe.getBounds(), { padding: [24, 24] });
    } else {
      carte.setView([34.0, 9.5], 6);
    }
  }

  const bouton = document.getElementById("utiliser-position");
  const message = document.getElementById("position-message");
  if (!bouton) return;
  bouton.addEventListener("click", function () {
    if (!navigator.geolocation) {
      ecrire("La géolocalisation n'est pas disponible sur ce navigateur.");
      return;
    }
    bouton.disabled = true;
    navigator.geolocation.getCurrentPosition(
      function (position) {
        trier(position.coords.latitude, position.coords.longitude);
        ecrire("Distances calculées depuis votre position. Elle n'est pas enregistrée.");
        bouton.disabled = false;
      },
      function () {
        ecrire("Position refusée ou indisponible. La recherche par ville reste utilisable.");
        bouton.disabled = false;
      },
      { enableHighAccuracy: false, timeout: 8000, maximumAge: 0 }
    );
  });

  function trier(latitude, longitude) {
    const liste = document.getElementById("liste-relais");
    if (!liste) return;
    const cartes = Array.from(liste.querySelectorAll(".relais-item"));
    cartes.forEach(function (carte) {
      const zoneDistance = carte.querySelector(".relais-distance");
      if (!carte.dataset.lat) {
        carte.dataset.km = "999999";
        if (zoneDistance) zoneDistance.textContent = "Distance indisponible : coordonnées manquantes.";
        return;
      }
      const km = haversine(latitude, longitude, Number(carte.dataset.lat), Number(carte.dataset.lng));
      carte.dataset.km = String(km);
      if (zoneDistance) zoneDistance.textContent = km.toFixed(1) + " km à vol d'oiseau";
    });
    cartes.sort(function (a, b) {
      return Number(a.dataset.km) - Number(b.dataset.km);
    });
    cartes.forEach(function (carte) {
      liste.appendChild(carte);
    });
  }

  function haversine(latitudeA, longitudeA, latitudeB, longitudeB) {
    const rayon = 6371;
    const rad = Math.PI / 180;
    const deltaLat = (latitudeB - latitudeA) * rad;
    const deltaLon = (longitudeB - longitudeA) * rad;
    const arc =
      Math.sin(deltaLat / 2) ** 2 +
      Math.cos(latitudeA * rad) * Math.cos(latitudeB * rad) * Math.sin(deltaLon / 2) ** 2;
    return 2 * rayon * Math.asin(Math.sqrt(arc));
  }

  function popup(point) {
    const lignes = [
      "<strong>" + echapper(point.nom) + "</strong>",
      echapper(point.adresse) + ", " + echapper(point.ville),
      echapper(point.gouvernorat),
      "Horaires : " + echapper(point.horaires),
      "Capacité maximale : " + echapper(point.capacite),
    ];
    if (point.disponibilite) lignes.push(echapper(point.disponibilite));
    lignes.push('<a href="' + echapper(point.url) + '">Voir les détails</a>');
    if (point.reserver) {
      lignes.push('<a href="' + echapper(point.reserver) + '">Réserver un créneau de dépôt</a>');
    }
    return lignes.filter(Boolean).join("<br>");
  }

  function popupRecommandation(point) {
    const lignes = [
      "<strong>" + echapper(point.rang) + ". " + echapper(point.nom) + "</strong>",
      echapper(point.ville),
      "Score " + echapper(point.score) + " %",
      echapper(point.explication),
    ];
    if (point.reserver) {
      lignes.push('<a href="' + echapper(point.reserver) + '">Réserver</a>');
    }
    return lignes.join("<br>");
  }

  function echapper(valeur) {
    return String(valeur || "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;");
  }

  function ecrire(texte) {
    if (message) message.textContent = texte;
  }
})();
