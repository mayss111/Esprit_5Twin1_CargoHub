/*
 * IA du M4 — bouton « Suggérer un prix » du formulaire d'offre.
 * Envoie le trajet choisi à /appels-offres/suggestion-prix/, pré-remplit le champ prix
 * et annonce le résultat (ou l'erreur) aux lecteurs d'écran via la zone aria-live.
 */
(() => {
  const form = document.getElementById("form-offre");
  const bouton = document.getElementById("btn-suggestion");
  if (!form || !bouton) return;
  const resultat = document.getElementById("suggestion-resultat");
  const champPrix = form.querySelector("[name=prix]");
  const libelle = bouton.innerHTML;

  bouton.addEventListener("click", async () => {
    const donnees = new FormData();
    donnees.append("csrfmiddlewaretoken", form.querySelector("[name=csrfmiddlewaretoken]").value);
    donnees.append("appel", form.dataset.appel);
    donnees.append("trajet", form.querySelector("[name=trajet]").value);

    bouton.disabled = true;
    bouton.setAttribute("aria-busy", "true");
    bouton.innerHTML = '<span class="spinner-border spinner-border-sm me-1" aria-hidden="true"></span> Calcul en cours…';
    resultat.className = "small mb-0";
    resultat.textContent = "Calcul en cours…";

    try {
      const reponse = await fetch(form.dataset.suggestionUrl, { method: "POST", body: donnees });
      const json = await reponse.json();
      if (!reponse.ok) throw new Error(json.erreur || "Le calcul du prix a échoué.");
      champPrix.value = json.prix;
      resultat.classList.add("text-success");
      resultat.textContent = `Prix suggéré : ${json.prix} DT — méthode : ${json.methode} (${json.duree_ms} ms). Vous pouvez l’ajuster.`;
      champPrix.focus();
    } catch (erreur) {
      resultat.classList.add("text-danger");
      resultat.textContent = erreur.message.startsWith("Unexpected") ? "Le calcul du prix a échoué." : erreur.message;
    } finally {
      bouton.disabled = false;
      bouton.removeAttribute("aria-busy");
      bouton.innerHTML = libelle;
    }
  });
})();
