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
  if (form instanceof HTMLFormElement && /\/supprimer\//.test(form.action) && !form.closest(".modal") && !form.dataset.suppressionConfirmee) {
    event.preventDefault();
    const cible = document.getElementById("modalSuppressionSinistre");
    if (cible && window.bootstrap?.Modal) {
      const modal = window.bootstrap.Modal.getOrCreateInstance(cible);
      const confirmer = cible.querySelector("form button[type=submit]");
      if (confirmer) {
        confirmer.onclick = () => {
          form.dataset.suppressionConfirmee = "1";
          modal.hide();
          form.submit();
        };
      }
      modal.show();
    } else if (window.confirm("Voulez-vous supprimer définitivement ce dossier ?")) {
      form.dataset.suppressionConfirmee = "1";
      form.submit();
    }
    return;
  }
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
  const bouton = event.submitter || form.querySelector("[type=submit]");
  const texteBouton = bouton?.textContent?.trim() || "";
  const confirmation = form.dataset.confirm || bouton?.dataset.confirm ||
    (/supprimer|annuler/i.test(texteBouton) ? `Confirmer l’action « ${texteBouton} » ?` : "");
  if (confirmation && !window.confirm(confirmation)) {
    event.preventDefault();
    return;
  }
  if (!form.matches("[data-ia]")) return;
  if (!bouton) return;
  bouton.disabled = true;
  bouton.classList.add("ia-chargement");
  bouton.setAttribute("aria-busy", "true");
  bouton.innerHTML =
    '<span class="spinner-border me-2" role="status" aria-hidden="true"></span>' +
    '<span aria-live="polite">' + (form.dataset.ia || "Traitement en cours…") + "</span>";
});

document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll(".is-invalid").forEach((champ) => {
    champ.setAttribute("aria-invalid", "true");
    const erreur = champ.closest(".mb-3, .form-group, .fieldWrapper")?.querySelector(".invalid-feedback, .errorlist");
    if (erreur) {
      if (!erreur.id) erreur.id = `${champ.id || "champ"}-erreur`;
      champ.setAttribute("aria-describedby", erreur.id);
    }
  });
  document.querySelectorAll(".alert").forEach((alerte) => {
    if (!alerte.getAttribute("role")) alerte.setAttribute("role", "status");
    alerte.setAttribute("aria-live", "polite");
  });

  document.querySelectorAll("[data-tts-text]").forEach((bouton) => {
    const definirEtatLecture = (icone, libelle) => {
      bouton.innerHTML = `<i class="bi ${icone}" aria-hidden="true"></i> <span>${libelle}</span>`;
      bouton.setAttribute("aria-label", libelle);
    };
    bouton.addEventListener("click", () => {
      if (!("speechSynthesis" in window) || typeof window.SpeechSynthesisUtterance !== "function") {
        definirEtatLecture("bi-volume-mute", "Audio indisponible");
        return;
      }
      if (window.speechSynthesis.speaking && !window.speechSynthesis.paused) {
        window.speechSynthesis.pause(); definirEtatLecture("bi-play-fill", "Reprendre"); return;
      }
      if (window.speechSynthesis.paused) {
        window.speechSynthesis.resume(); definirEtatLecture("bi-pause-fill", "Pause"); return;
      }
      window.speechSynthesis.cancel();
      const utterance = new SpeechSynthesisUtterance(bouton.dataset.ttsText);
      utterance.lang = "fr-FR";
      utterance.onend = () => { definirEtatLecture("bi-volume-up", "Écouter"); };
      utterance.onerror = () => { definirEtatLecture("bi-volume-up", "Écouter"); };
      window.speechSynthesis.speak(utterance);
      definirEtatLecture("bi-pause-fill", "Pause");
    });
  });
});
