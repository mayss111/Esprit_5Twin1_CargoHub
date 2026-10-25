(function () {
  var racine = document.querySelector("[data-occupation-url]");
  if (!racine) {
    return;
  }
  var url = racine.getAttribute("data-occupation-url");

  function texte(selecteur, valeur) {
    var noeud = document.querySelector(selecteur);
    if (noeud && valeur !== undefined && valeur !== null) {
      noeud.textContent = valeur;
    }
  }

  function appliquer(data) {
    ["entrepots_actifs", "capacite", "reserve", "disponible", "taux", "actives"].forEach(function (cle) {
      texte('[data-stat="' + cle + '"]', data[cle]);
    });
    (data.lignes || []).forEach(function (ligne) {
      var tr = document.querySelector('tr[data-entrepot="' + ligne.id + '"]');
      if (!tr) {
        return;
      }
      ["capacite", "reserve", "disponible"].forEach(function (col) {
        var cellule = tr.querySelector('[data-col="' + col + '"]');
        if (cellule) {
          cellule.textContent = ligne[col] + " m³";
        }
      });
      var taux = tr.querySelector("[data-col='taux-valeur']");
      var barre = tr.querySelector(".progress-bar");
      var progress = tr.querySelector(".progress");
      if (taux) {
        taux.textContent = ligne.taux === null ? "—" : ligne.taux + " %";
      }
      if (barre && ligne.barre !== null) {
        barre.style.width = ligne.barre + "%";
      }
      if (progress && ligne.barre !== null) {
        progress.setAttribute("aria-valuenow", ligne.barre);
      }
    });
  }

  window.setInterval(function () {
    window
      .fetch(url + window.location.search, {
        headers: { Accept: "application/json" },
        credentials: "same-origin",
      })
      .then(function (reponse) {
        return reponse.ok ? reponse.json() : null;
      })
      .then(function (data) {
        if (data) {
          appliquer(data);
        }
      })
      .catch(function () {});
  }, 25000);
})();
