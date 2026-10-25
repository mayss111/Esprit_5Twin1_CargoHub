/*
 * CargoHub — petits comportements communs.
 *
 * Indicateur de chargement pour les appels IA (grille : « Expérience utilisateur ») :
 *   <form method="post" data-ia="Analyse en cours…"> … <button type="submit">Analyser</button> </form>
 * Au clic, le bouton est désactivé et affiche un spinner + le texte donné,
 * annoncé aussi aux lecteurs d'écran (aria-live).
 */
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
