/**
 * Saisie vocale CargoHub — Web Speech API, entièrement côté navigateur.
 *
 * L'audio et la transcription ne sont pas envoyés à Django.
 * Le formulaire n'est jamais soumis automatiquement.
 * Après une dictée, le mot de passe s'affiche dans le champ pour vérification.
 * Un bouton œil permet de le masquer à nouveau.
 * Les champs cachés, fichiers et cases sont ignorés.
 */
(function (root, factory) {
  "use strict";

  const api = factory();

  if (typeof module === "object" && module.exports) {
    module.exports = api;
  }

  if (root) {
    root.CargoHubVoice = api;
  }

  if (root && root.document) {
    const demarrer = function () {
      api.monter(root.document);
    };
    if (root.document.readyState === "loading") {
      root.document.addEventListener("DOMContentLoaded", demarrer);
    } else {
      demarrer();
    }
  }
})(typeof window !== "undefined" ? window : typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  const LANGUES = ["fr-FR", "ar-TN", "en-US"];
  const LANGUE_DEFAUT = "fr-FR";
  const CLE_LANGUE = "cargohub.voice.lang";
  const TYPES_BLOQUES = new Set([
    "hidden",
    "file",
    "checkbox",
    "radio",
    "submit",
    "button",
    "reset",
    "image",
  ]);

  const MESSAGE_INDISPONIBLE =
    "La dictée vocale n'est pas disponible dans ce navigateur. Utilisez Chrome ou Edge, ou remplissez le formulaire au clavier.";

  let sessionActive = null;

  function langueAutorisee(code) {
    return LANGUES.includes(code) ? code : LANGUE_DEFAUT;
  }

  function champEligible(input) {
    if (!input) return false;
    const type = String(input.type || "text").toLowerCase();
    if (TYPES_BLOQUES.has(type)) return false;
    const nom = String(input.name || "").toLowerCase();
    if (nom.includes("csrf")) return false;
    return true;
  }

  function normalizeEmailTranscript(texte) {
    const brut = String(texte || "").trim();
    if (!brut) return "";

    const compact = brut.replace(/\s+/g, "");
    const contientMotcle = /\b(arobase|arobas|point|dot|tiret|dash|hyphen|underscore|chez)\b/i.test(brut);
    if (!contientMotcle && /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(compact)) {
      return compact.toLowerCase();
    }

    let sortie = ` ${brut.toLowerCase()} `;
    sortie = sortie.replace(/\s+(tiret du bas|trait de soulignement|underscore|tiret bas)\s+/g, " _ ");
    sortie = sortie.replace(/\s+(arobase|arobas|at|chez)\s+/g, " @ ");
    sortie = sortie.replace(/\s+(point|dot)\s+/g, " . ");
    sortie = sortie.replace(/\s+(tiret|dash|hyphen)\s+/g, " - ");
    sortie = sortie.replace(/\s+/g, "");
    return sortie;
  }

  function messageErreur(code, langue) {
    const langueCourante = langueAutorisee(langue);
    const messages = {
      "not-allowed":
        "Accès au microphone refusé. Autorisez-le dans le navigateur, ou saisissez le champ manuellement.",
      "service-not-allowed":
        "Le microphone est bloqué par le navigateur. Saisissez le champ manuellement.",
      "no-speech": "Aucune voix détectée. Réessayez en parlant juste après l'invitation.",
      "audio-capture":
        "Aucun microphone n'a été détecté. Vérifiez le branchement, ou saisissez le champ au clavier.",
      network:
        "La reconnaissance vocale a besoin d'une connexion. Vous pouvez remplir le champ manuellement.",
      "language-not-supported":
        langueCourante === "ar-TN"
          ? "L'arabe tunisien n'est pas pris en charge par ce navigateur. Choisissez le français ou l'anglais."
          : "Cette langue n'est pas prise en charge par ce navigateur. Choisissez une autre langue de dictée.",
      "bad-grammar": "La phrase n'a pas pu être interprétée. Réessayez, ou modifiez le champ à la main.",
      aborted: "",
    };
    if (Object.prototype.hasOwnProperty.call(messages, code)) {
      return messages[code];
    }
    return "La dictée a échoué. Vous pouvez modifier le champ manuellement.";
  }

  function formaterTranscription(texte, input) {
    const brut = String(texte || "").replace(/\s+/g, " ").trim();
    const type = String(input.type || "").toLowerCase();
    const nom = String(input.name || "").toLowerCase();
    if (type === "email" || nom === "email" || nom === "username") {
      return normalizeEmailTranscript(brut);
    }
    return brut;
  }

  function reconnaissanceDisponible() {
    if (typeof window === "undefined") return null;
    return window.SpeechRecognition || window.webkitSpeechRecognition || null;
  }

  function libelle(input) {
    if (input.labels && input.labels.length > 0) {
      return input.labels[0].textContent.replace(/\s+/g, " ").replace(/\*/g, "").trim();
    }
    return input.getAttribute("aria-label") || input.name || "ce champ";
  }

  function definirStatut(element, message, etat) {
    element.textContent = message;
    element.classList.remove("is-live", "is-ok", "is-error");
    if (etat === "live") element.classList.add("is-live");
    if (etat === "ok") element.classList.add("is-ok");
    if (etat === "error") element.classList.add("is-error");
  }

  function lireLangue(stockage) {
    try {
      return langueAutorisee(stockage.getItem(CLE_LANGUE));
    } catch (erreur) {
      return LANGUE_DEFAUT;
    }
  }

  function ecrireLangue(stockage, langue) {
    try {
      stockage.setItem(CLE_LANGUE, langueAutorisee(langue));
    } catch (erreur) {
      /* stockage indisponible : la langue reste celle du sélecteur */
    }
  }

  function estSecret(input) {
    return input.dataset.voiceSecret === "1";
  }

  function mettreAJourOeil(input, visible) {
    const oeil = input.parentNode && input.parentNode.querySelector("[data-voice-reveal]");
    if (!oeil) return;
    oeil.setAttribute("aria-pressed", visible ? "true" : "false");
    oeil.setAttribute("aria-label", `${visible ? "Masquer" : "Afficher"} le champ ${libelle(input)}`);
    const icone = oeil.querySelector("i");
    if (icone) icone.className = visible ? "bi bi-eye-slash" : "bi bi-eye";
  }

  function afficherSecret(input) {
    if (!estSecret(input)) return;
    input.type = "text";
    mettreAJourOeil(input, true);
  }

  function basculerVisibilite(input) {
    const visible = String(input.type || "").toLowerCase() === "password";
    input.type = visible ? "text" : "password";
    mettreAJourOeil(input, visible);
  }

  function reinitialiserBouton(bouton, input) {
    bouton.classList.remove("is-listening");
    bouton.setAttribute("aria-pressed", "false");
    bouton.setAttribute("aria-label", `Dicter le champ ${libelle(input)}`);
    const icone = bouton.querySelector("i");
    if (icone) icone.className = "bi bi-mic";
  }

  function arreter(parUtilisateur) {
    if (!sessionActive) return;
    sessionActive.stoppedByUser = parUtilisateur;
    try {
      sessionActive.recognition.abort();
    } catch (erreur) {
      /* la session est déjà terminée */
    }
  }

  function demarrer(input, bouton, statut, select) {
    const Ctor = reconnaissanceDisponible();
    if (!Ctor) {
      definirStatut(statut, MESSAGE_INDISPONIBLE, "error");
      return;
    }

    arreter(true);

    const recognition = new Ctor();
    const session = {
      recognition: recognition,
      bouton: bouton,
      statut: statut,
      input: input,
      stoppedByUser: false,
      gotResult: false,
      gotError: false,
    };
    sessionActive = session;

    const langue = select ? langueAutorisee(select.value) : LANGUE_DEFAUT;
    recognition.lang = langue;
    recognition.continuous = false;
    recognition.interimResults = true;
    recognition.maxAlternatives = 1;

    recognition.onstart = function () {
      bouton.classList.add("is-listening");
      bouton.setAttribute("aria-pressed", "true");
      bouton.setAttribute("aria-label", `Arrêter la dictée du champ ${libelle(input)}`);
      const icone = bouton.querySelector("i");
      if (icone) icone.className = "bi bi-mic-fill";
      definirStatut(statut, "Parlez maintenant...", "live");
    };

    recognition.onresult = function (event) {
      let finalText = "";
      for (let i = event.resultIndex; i < event.results.length; i += 1) {
        if (event.results[i].isFinal) {
          finalText += event.results[i][0].transcript;
        }
      }
      const propre = finalText.replace(/\s+/g, " ").trim();
      if (!propre) return;
      session.gotResult = true;
      input.value = formaterTranscription(propre, input);
      input.dispatchEvent(new Event("input", { bubbles: true }));
      input.dispatchEvent(new Event("change", { bubbles: true }));
      if (estSecret(input)) afficherSecret(input);
      definirStatut(
        statut,
        estSecret(input) ? "Mot de passe affiché. Vérifiez-le avant d'envoyer." : "Texte reconnu",
        "ok",
      );
    };

    recognition.onerror = function (event) {
      session.gotError = true;
      if (event.error === "aborted" && session.stoppedByUser) return;
      const message = messageErreur(event.error, langue);
      if (message) definirStatut(statut, message, "error");
    };

    recognition.onend = function () {
      reinitialiserBouton(bouton, input);
      if (sessionActive === session) sessionActive = null;
      if (!session.gotResult && !session.stoppedByUser && !session.gotError) {
        definirStatut(
          statut,
          "Aucune voix détectée. Réessayez ou saisissez le champ manuellement.",
          "error",
        );
      }
    };

    try {
      recognition.start();
    } catch (erreur) {
      session.gotError = true;
      if (sessionActive === session) sessionActive = null;
      reinitialiserBouton(bouton, input);
      definirStatut(
        statut,
        "Impossible de démarrer le microphone. Réessayez ou saisissez le champ manuellement.",
        "error",
      );
    }
  }

  function basculer(input, bouton, statut, select) {
    if (sessionActive && sessionActive.input === input) {
      const zone = sessionActive.statut;
      arreter(true);
      definirStatut(
        zone,
        "Écoute interrompue. Le texte déjà reconnu reste modifiable.",
        "live",
      );
      return;
    }
    demarrer(input, bouton, statut, select);
  }

  function attacher(input, select) {
    if (input.dataset.voiceBound === "1" || !champEligible(input)) return;
    input.dataset.voiceBound = "1";
    input.dir = "auto";
    if (String(input.type || "").toLowerCase() === "password") {
      input.dataset.voiceSecret = "1";
    }

    const enveloppe = input.ownerDocument.createElement("div");
    enveloppe.className = "voice-field";
    input.parentNode.insertBefore(enveloppe, input);
    enveloppe.appendChild(input);

    const bouton = input.ownerDocument.createElement("button");
    bouton.type = "button";
    bouton.className = "btn-voice";
    bouton.setAttribute("aria-pressed", "false");
    bouton.setAttribute("aria-label", `Dicter le champ ${libelle(input)}`);
    bouton.innerHTML = '<i class="bi bi-mic" aria-hidden="true"></i>';

    const statut = input.ownerDocument.createElement("p");
    statut.className = "voice-status";
    statut.setAttribute("role", "status");
    statut.setAttribute("aria-live", "polite");
    statut.id = `${input.id || input.name}-voice-status`;
    bouton.setAttribute("aria-describedby", statut.id);

    enveloppe.appendChild(bouton);
    if (estSecret(input)) {
      const oeil = input.ownerDocument.createElement("button");
      oeil.type = "button";
      oeil.className = "btn-voice";
      oeil.setAttribute("data-voice-reveal", "true");
      oeil.setAttribute("aria-pressed", "false");
      oeil.setAttribute("aria-label", `Afficher le champ ${libelle(input)}`);
      oeil.innerHTML = '<i class="bi bi-eye" aria-hidden="true"></i>';
      enveloppe.appendChild(oeil);
      oeil.addEventListener("click", function () {
        basculerVisibilite(input);
      });
    }
    enveloppe.insertAdjacentElement("afterend", statut);

    bouton.addEventListener("click", function () {
      basculer(input, bouton, statut, select);
    });
  }

  function monter(doc) {
    const repli = doc.querySelectorAll("[data-voice-fallback]");
    const controles = doc.querySelectorAll("[data-voice-controls]");
    const disponible = Boolean(reconnaissanceDisponible());

    if (!disponible) {
      repli.forEach(function (element) {
        element.classList.remove("d-none");
      });
      controles.forEach(function (element) {
        element.classList.add("d-none");
      });
      return { actif: false };
    }

    const select = doc.querySelector("[data-voice-lang]");
    const stockage = typeof window !== "undefined" ? window.localStorage : null;
    if (select && stockage) {
      const sauvee = lireLangue(stockage);
      if (Array.prototype.some.call(select.options, function (option) { return option.value === sauvee; })) {
        select.value = sauvee;
      }
      select.addEventListener("change", function () {
        ecrireLangue(stockage, select.value);
      });
    }

    doc.querySelectorAll("form[data-voice-fields]").forEach(function (form) {
      const noms = (form.getAttribute("data-voice-fields") || "")
        .split(",")
        .map(function (nom) { return nom.trim(); })
        .filter(Boolean);
      noms.forEach(function (nom) {
        const selecteur = typeof CSS !== "undefined" && CSS.escape ? CSS.escape(nom) : nom.replace(/"/g, "");
        const input = form.querySelector(`[name="${selecteur}"]`);
        if (input) attacher(input, select);
      });
    });

    if (!doc.documentElement.dataset.voiceEscape) {
      doc.documentElement.dataset.voiceEscape = "1";
      doc.addEventListener("keydown", function (event) {
        if (event.key === "Escape" && sessionActive) {
          const zone = sessionActive.statut;
          arreter(true);
          definirStatut(
            zone,
            "Écoute interrompue. Vous pouvez modifier le champ ou relancer le microphone.",
            "live",
          );
        }
      });
    }

    return { actif: true };
  }

  return {
    LANGUES: LANGUES,
    LANGUE_DEFAUT: LANGUE_DEFAUT,
    langueAutorisee: langueAutorisee,
    champEligible: champEligible,
    normalizeEmailTranscript: normalizeEmailTranscript,
    messageErreur: messageErreur,
    formaterTranscription: formaterTranscription,
    monter: monter,
  };
});
