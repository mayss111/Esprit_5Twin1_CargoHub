/*
 * CargoHub — petits comportements communs.
 *
 * Indicateur de chargement pour les appels IA (grille : « Expérience utilisateur ») :
 *   <form method="post" data-ia="Analyse en cours…"> … <button type="submit">Analyser</button> </form>
 * Au clic, le bouton est désactivé et affiche un spinner + le texte donné,
 * annoncé aussi aux lecteurs d'écran (aria-live).
 */
document.addEventListener("click", (event) => {
  const bouton = event.target.closest("button, input");
  const form = bouton && bouton.form;
  if (!form || bouton.type !== "submit" || !form.matches("[data-ia]")) return;
  form.querySelectorAll("[data-soumission]").forEach((champ) => champ.remove());
  if (!bouton.name) return;
  const champ = document.createElement("input");
  champ.type = "hidden";
  champ.name = bouton.name;
  champ.value = bouton.value;
  champ.setAttribute("data-soumission", "1");
  form.appendChild(champ);
});

document.addEventListener("submit", (event) => {
  const form = event.target;
  if (!form.matches("[data-ia]")) return;
  const bouton = event.submitter || form.querySelector("[type=submit]");
  if (!bouton) return;
  bouton.disabled = true;
  bouton.classList.add("ia-chargement");
  bouton.setAttribute("aria-busy", "true");
  bouton.innerHTML =
    '<span class="spinner-border me-2" role="status" aria-hidden="true"></span>' +
    '<span aria-live="polite">' + (form.dataset.ia || "Traitement en cours…") + "</span>";
});
