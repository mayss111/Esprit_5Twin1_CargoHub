/*
 * Taille du texte, langue et lecture vocale. Présent sur toutes les pages.
 */
(function () {
  const ECHELLES = ["87.5%", "100%", "112.5%", "125%", "137.5%", "150%"];
  const VOIX = { fr: "fr-FR", en: "en-GB", ar: "ar-SA" };
  const CLE = "cargohub-texte";

  function echelleActuelle() {
    const valeur = document.documentElement.style.fontSize;
    const indice = ECHELLES.indexOf(valeur);
    return indice === -1 ? 1 : indice;
  }

  function appliquer(indice) {
    const borne = Math.min(ECHELLES.length - 1, Math.max(0, indice));
    const valeur = ECHELLES[borne];
    document.documentElement.style.fontSize = valeur === "100%" ? "" : valeur;
    try {
      localStorage.setItem(CLE, valeur === "100%" ? "" : valeur);
    } catch (erreur) {
      /* le réglage reste valable pour cette page */
    }
  }

  const reduire = document.getElementById("texte-reduire");
  const agrandir = document.getElementById("texte-agrandir");
  if (reduire) reduire.addEventListener("click", () => appliquer(echelleActuelle() - 1));
  if (agrandir) agrandir.addEventListener("click", () => appliquer(echelleActuelle() + 1));

  const lecture = document.getElementById("lecture-vocale");
  const message = document.getElementById("lecture-message");
  if (!lecture) return;

  function icone(nom) {
    const balise = lecture.querySelector("i");
    if (balise) balise.className = "bi bi-" + nom;
  }

  function arreter() {
    if (window.speechSynthesis) window.speechSynthesis.cancel();
    lecture.setAttribute("aria-pressed", "false");
    lecture.setAttribute("aria-label", lecture.dataset.lire);
    icone("volume-up-fill");
  }

  lecture.addEventListener("click", () => {
    if (!window.speechSynthesis) {
      if (message) message.textContent = lecture.dataset.indisponible;
      return;
    }
    if (lecture.getAttribute("aria-pressed") === "true") {
      arreter();
      return;
    }
    const zone = document.getElementById("contenu");
    const texte = (zone ? zone.innerText : "").replace(/\s+/g, " ").trim().slice(0, 12000);
    if (!texte) return;
    const phrase = new SpeechSynthesisUtterance(texte);
    phrase.lang = VOIX[lecture.dataset.langue] || "fr-FR";
    phrase.onend = arreter;
    phrase.onerror = arreter;
    window.speechSynthesis.cancel();
    lecture.setAttribute("aria-pressed", "true");
    lecture.setAttribute("aria-label", lecture.dataset.stop);
    icone("stop-fill");
    window.speechSynthesis.speak(phrase);
  });
})();
