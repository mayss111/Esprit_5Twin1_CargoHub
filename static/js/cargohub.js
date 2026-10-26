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

function messageControle(champ) {
  if (champ.disabled || champ.type === "hidden" || champ.type === "submit" || champ.type === "button") return "";
  const valeur = (champ.value || "").trim();
  const obligatoire = champ.required;
  if (champ.tagName === "SELECT") {
    return obligatoire && !valeur ? champ.title || "Choisissez une valeur dans la liste." : "";
  }
  if (champ.type === "file") {
    return obligatoire && champ.files.length === 0 ? "Choisissez un fichier." : "";
  }
  if (obligatoire && !valeur) return "Ce champ est obligatoire.";
  if (!valeur) return "";
  const minlength = Number(champ.getAttribute("minlength") || 0);
  if (minlength && valeur.length < minlength) return `Saisissez au moins ${minlength} caractères.`;
  const maxlength = Number(champ.getAttribute("maxlength") || 0);
  if (maxlength && valeur.length > maxlength) return `${maxlength} caractères maximum.`;
  const pattern = champ.getAttribute("pattern");
  if (pattern && !new RegExp(`^(?:${pattern})$`).test(valeur)) {
    return champ.title || "Le format saisi n’est pas accepté.";
  }
  if (champ.type === "email" && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(valeur)) {
    return "Saisissez une adresse email valide.";
  }
  if (champ.type === "number") {
    const nombre = Number(valeur);
    if (Number.isNaN(nombre)) return "Saisissez un nombre.";
    if (champ.min !== "" && nombre < Number(champ.min)) return champ.title || `La valeur minimum est ${champ.min}.`;
    if (champ.max !== "" && nombre > Number(champ.max)) return champ.title || `La valeur maximum est ${champ.max}.`;
  }
  return "";
}

document.addEventListener("submit", (event) => {
  const form = event.target;
  if (!(form instanceof HTMLFormElement) || !form.hasAttribute("data-controle")) return;
  form.querySelectorAll(".controle-erreur").forEach((erreur) => erreur.remove());
  form.querySelectorAll(".is-invalid").forEach((champ) => {
    champ.classList.remove("is-invalid");
    champ.removeAttribute("aria-invalid");
  });
  let invalide = false;
  form.querySelectorAll("input, select, textarea").forEach((champ) => {
    const message = messageControle(champ);
    if (!message) return;
    invalide = true;
    champ.classList.add("is-invalid");
    champ.setAttribute("aria-invalid", "true");
    const erreur = document.createElement("div");
    erreur.className = "invalid-feedback d-block controle-erreur";
    erreur.setAttribute("role", "alert");
    erreur.textContent = message;
    champ.insertAdjacentElement("afterend", erreur);
  });
  if (!invalide) return;
  event.preventDefault();
  event.stopImmediatePropagation();
  const premier = form.querySelector(".is-invalid");
  if (premier) premier.focus();
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
