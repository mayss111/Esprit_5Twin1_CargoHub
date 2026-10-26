(function () {
  const bloc = document.getElementById("assistant-saisie");
  const bouton = document.getElementById("assistant-remplir");
  const zone = document.getElementById("assistant-description");
  const chargement = document.getElementById("assistant-chargement");
  const propositions = document.getElementById("assistant-propositions");
  if (!bloc || !bouton || !zone) return;

  bouton.addEventListener("click", function () {
    if (bouton.disabled) return;
    const jeton = bloc.querySelector("[name=csrfmiddlewaretoken]");
    bouton.disabled = true;
    chargement.classList.remove("d-none");
    chargement.classList.add("d-flex");
    propositions.innerHTML = "";

    fetch(bloc.dataset.url, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": jeton ? jeton.value : "",
      },
      body: JSON.stringify({ description: zone.value }),
    })
      .then(function (reponse) {
        return reponse.json().then(function (data) {
          return { ok: reponse.ok, status: reponse.status, data: data };
        });
      })
      .then(function (resultat) {
        if (resultat.status === 202 && resultat.data.statut === "EN_COURS") {
          return attendre(resultat.data.jeton);
        }
        if (!resultat.ok) {
          afficherMessage(resultat.data.erreur || "L'assistant n'a pas pu analyser le texte.", true);
          return;
        }
        remplir(resultat.data);
      })
      .catch(function () {
        afficherMessage("L'assistant n'a pas répondu. Réessayez ou saisissez le formulaire.", true);
      })
      .finally(function () {
        bouton.disabled = false;
        chargement.classList.add("d-none");
        chargement.classList.remove("d-flex");
      });
  });

  function attendre(jeton) {
    const url = bloc.dataset.statutUrl + "?jeton=" + encodeURIComponent(jeton);
    let essais = 0;
    return new Promise(function (resolve) {
      const tour = function () {
        essais += 1;
        fetch(url, { credentials: "same-origin", headers: { Accept: "application/json" } })
          .then(function (reponse) {
            return reponse.json().then(function (data) {
              return { ok: reponse.ok, data: data };
            });
          })
          .then(function (resultat) {
            if (resultat.data.statut === "PRET") {
              remplir(resultat.data.resultat);
              resolve();
              return;
            }
            if (resultat.data.statut === "ERREUR" || !resultat.ok) {
              afficherMessage(resultat.data.erreur || "L'assistant n'a pas pu analyser le texte.", true);
              resolve();
              return;
            }
            if (essais >= 110) {
              afficherMessage("L'assistant met trop de temps. Réessayez ou saisissez le formulaire.", true);
              resolve();
              return;
            }
            setTimeout(tour, 1000);
          })
          .catch(function () {
            if (essais >= 110) {
              afficherMessage("L'assistant n'a pas répondu. Réessayez ou saisissez le formulaire.", true);
              resolve();
              return;
            }
            setTimeout(tour, 1000);
          });
      };
      setTimeout(tour, 1000);
    });
  }

  function remplir(data) {
    Object.entries(data.champs || {}).forEach(function (entree) {
      ecrire("id_" + entree[0], entree[1]);
    });
    const articles = data.articles || [];
    const total = document.getElementById("id_articles-TOTAL_FORMS");
    const ajouter = document.getElementById("ajouter-article");
    articles.forEach(function (article, index) {
      while (total && ajouter && Number(total.value) <= index) ajouter.click();
      const prefixe = "id_articles-" + index + "-";
      ecrire(prefixe + "designation", article.designation);
      ecrire(prefixe + "description", article.description);
      ecrire(prefixe + "type_marchandise", article.type_marchandise);
      ecrire(prefixe + "quantite", nombreChamp(article.quantite));
      ecrire(prefixe + "poids_kg", nombreChamp(article.poids_kg));
      ecrire(prefixe + "volume_m3", nombreChamp(article.volume_m3));
      ecrire(prefixe + "valeur_declaree", nombreChamp(article.valeur_declaree));
      const fragile = document.getElementById(prefixe + "fragile");
      if (fragile && article.fragile === true) fragile.checked = true;
      if (fragile && article.fragile === false) fragile.checked = false;
    });
    afficherPropositions(data);
  }

  function nombreChamp(valeur) {
    if (valeur === null || valeur === undefined || valeur === "") return "";
    return String(valeur).trim().replace(/\s/g, "").replace(",", ".");
  }

  function formaterNombre(valeur) {
    const normalise = nombreChamp(valeur);
    const negatif = normalise.startsWith("-");
    const texte = negatif ? normalise.slice(1) : normalise;
    const morceaux = texte.split(".");
    const entier = morceaux[0].replace(/\B(?=(\d{3})+(?!\d))/g, " ");
    const decimales = (morceaux[1] || "").replace(/0+$/, "");
    return (negatif ? "-" : "") + entier + (decimales ? "," + decimales : "");
  }

  function formulerTotaux(totaux) {
    if (!totaux) return "";
    const morceaux = [];
    if (totaux.poids_kg != null && totaux.poids_kg !== "") morceaux.push(formaterNombre(totaux.poids_kg) + " kg");
    if (totaux.volume_m3 != null && totaux.volume_m3 !== "") morceaux.push(formaterNombre(totaux.volume_m3) + " m³");
    if (totaux.valeur_declaree != null && totaux.valeur_declaree !== "") {
      morceaux.push(formaterNombre(totaux.valeur_declaree) + " DT");
    }
    if (morceaux.length === 3) return "Totaux calculés : " + morceaux[0] + ", " + morceaux[1] + " et " + morceaux[2] + ".";
    if (morceaux.length) return "Totaux calculés : " + morceaux.join(", ") + ".";
    return "";
  }

  function ecrire(id, valeur) {
    const champ = document.getElementById(id);
    if (!champ || valeur === null || valeur === undefined || valeur === "") return;
    champ.value = valeur;
  }

  function afficherPropositions(data) {
    const lignes = [];
    (data.articles || []).forEach(function (article) {
      const details = [article.designation];
      if (article.quantite) details.push("quantité " + article.quantite);
      if (article.unite) details.push(article.unite);
      if (article.type_marchandise) details.push(article.type_marchandise);
      if (article.poids_kg != null && article.poids_kg !== "") details.push(formaterNombre(article.poids_kg) + " kg");
      if (article.volume_m3 != null && article.volume_m3 !== "") details.push(formaterNombre(article.volume_m3) + " m³");
      if (article.valeur_declaree != null && article.valeur_declaree !== "") {
        details.push(formaterNombre(article.valeur_declaree) + " DT");
      }
      if (article.fragile === true) details.push("fragile");
      if (article.fragile === false) details.push("non fragile");
      lignes.push("<li>" + echapper(details.join(" — ")) + "</li>");
    });
    const totaux = formulerTotaux(data.totaux);
    if (totaux) lignes.push("<li>" + echapper(totaux) + "</li>");
    if (data.poids_total_declare && !(data.totaux && data.totaux.poids_kg != null)) {
      lignes.push("<li>Poids total déclaré : " + echapper(String(data.poids_total_declare)) + " kg, non réparti.</li>");
    }
    (data.informations_manquantes || []).forEach(function (info) {
      lignes.push("<li>À compléter : " + echapper(info) + "</li>");
    });
    (data.avertissements || []).forEach(function (info) {
      lignes.push("<li>" + echapper(info) + "</li>");
    });
    if (typeof data.duree_ms === "number") {
      lignes.push("<li>Réponse de l'assistant en " + data.duree_ms + " ms.</li>");
    }
    propositions.innerHTML = '<div class="alert alert-warning mb-0" role="status"><ul class="mb-0">' + lignes.join("") + "</ul></div>";
  }

  function afficherMessage(message, erreur) {
    const classe = erreur ? "alert-danger" : "alert-warning";
    propositions.innerHTML = '<div class="alert ' + classe + ' mb-0" role="alert">' + echapper(message) + "</div>";
  }

  function echapper(valeur) {
    return String(valeur)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;");
  }
})();
