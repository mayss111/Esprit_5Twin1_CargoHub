const assert = require("node:assert/strict");
const voice = require("./voice_input.js");

assert.deepEqual(voice.LANGUES, ["fr-FR", "ar-TN", "en-US"]);
assert.equal(voice.langueAutorisee("ar-TN"), "ar-TN");
assert.equal(voice.langueAutorisee("xx-XX"), "fr-FR");
assert.equal(voice.langueAutorisee(null), "fr-FR");

assert.equal(
  voice.normalizeEmailTranscript("Ines point Ben arobase Gmail point com"),
  "ines.ben@gmail.com",
);
assert.equal(voice.normalizeEmailTranscript("sami@atelier.tn"), "sami@atelier.tn");
assert.equal(
  voice.normalizeEmailTranscript("karim at transport dot tn"),
  "karim@transport.tn",
);
assert.equal(voice.normalizeEmailTranscript(""), "");

assert.equal(voice.champEligible({ type: "password", name: "password" }), true);
assert.equal(voice.champEligible({ type: "password", name: "password1" }), true);
assert.equal(voice.champEligible({ type: "password", name: "password2" }), true);
assert.equal(voice.champEligible({ type: "hidden", name: "csrfmiddlewaretoken" }), false);
assert.equal(voice.champEligible({ type: "radio", name: "role" }), false);
assert.equal(voice.champEligible({ type: "email", name: "email" }), true);
assert.equal(voice.champEligible({ type: "email", name: "username" }), true);
assert.equal(voice.champEligible({ type: "text", name: "first_name" }), true);
assert.equal(voice.champEligible(null), false);

assert.equal(
  voice.formaterTranscription("Sami point atelier arobase test point tn", { type: "email", name: "username" }),
  "sami.atelier@test.tn",
);
assert.equal(
  voice.formaterTranscription("  Ines   Ben  ", { type: "text", name: "first_name" }),
  "Ines Ben",
);
assert.equal(
  voice.formaterTranscription("Cargo Hub 2026", { type: "password", name: "password" }),
  "Cargo Hub 2026",
);

assert.match(voice.messageErreur("not-allowed", "fr-FR"), /microphone refusé/i);
assert.match(voice.messageErreur("service-not-allowed", "en-US"), /bloqué/i);
assert.match(voice.messageErreur("no-speech", "fr-FR"), /Aucune voix/);
assert.match(voice.messageErreur("audio-capture", "fr-FR"), /Aucun microphone/);
assert.match(voice.messageErreur("network", "fr-FR"), /connexion/);
assert.match(voice.messageErreur("language-not-supported", "ar-TN"), /arabe tunisien/i);
assert.match(voice.messageErreur("language-not-supported", "en-US"), /pas prise en charge/i);
assert.equal(voice.messageErreur("aborted", "fr-FR"), "");
assert.match(voice.messageErreur("inconnu", "fr-FR"), /manuellement/);

const source = require("node:fs").readFileSync(__filename.replace(/\.test\.js$/, ".js"), "utf8");
assert.equal(source.includes(".submit("), false);
assert.equal(source.includes("requestSubmit"), false);

function creerElement(tag) {
  const node = {
    tagName: tag.toUpperCase(),
    children: [],
    parentNode: null,
    attrs: {},
    dataset: {},
    textContent: "",
    value: "",
    type: tag === "input" ? "text" : "",
    name: "",
    id: "",
    dir: "",
    labels: [],
    options: [],
    ownerDocument: null,
    listeners: {},
    _class: new Set(),
  };
  node.classList = {
    add(classe) { node._class.add(classe); },
    remove(classe) { node._class.delete(classe); },
    contains(classe) { return node._class.has(classe); },
  };
  Object.defineProperty(node, "className", {
    get() { return [...node._class].join(" "); },
    set(valeur) { node._class = new Set(String(valeur).split(/\s+/).filter(Boolean)); },
  });
  Object.defineProperty(node, "innerHTML", {
    set(html) {
      node.children = [];
      const trouve = /<i\b[^>]*class="([^"]*)"/.exec(html);
      if (trouve) {
        const icone = creerElement("i");
        icone.className = trouve[1];
        node.appendChild(icone);
      }
    },
  });
  node.setAttribute = (cle, valeur) => {
    node.attrs[cle] = String(valeur);
    if (cle === "id") node.id = String(valeur);
    if (cle === "name") node.name = String(valeur);
    if (cle === "type") node.type = String(valeur);
  };
  node.getAttribute = (cle) => (Object.prototype.hasOwnProperty.call(node.attrs, cle) ? node.attrs[cle] : null);
  node.addEventListener = (type, fn) => { (node.listeners[type] ||= []).push(fn); };
  node.dispatchEvent = (event) => {
    (node.listeners[event.type] || []).forEach((fn) => fn(event));
    return true;
  };
  const detacher = (enfant) => {
    if (!enfant.parentNode) return;
    const index = enfant.parentNode.children.indexOf(enfant);
    if (index >= 0) enfant.parentNode.children.splice(index, 1);
  };
  node.appendChild = (enfant) => {
    detacher(enfant);
    enfant.parentNode = node;
    node.children.push(enfant);
    return enfant;
  };
  node.insertBefore = (enfant, reference) => {
    detacher(enfant);
    enfant.parentNode = node;
    const index = node.children.indexOf(reference);
    if (index === -1) node.children.push(enfant);
    else node.children.splice(index, 0, enfant);
    return enfant;
  };
  node.insertAdjacentElement = (position, enfant) => {
    if (position !== "afterend" || !node.parentNode) return null;
    detacher(enfant);
    const index = node.parentNode.children.indexOf(node);
    enfant.parentNode = node.parentNode;
    node.parentNode.children.splice(index + 1, 0, enfant);
    return enfant;
  };
  node.querySelector = (selecteur) => chercher(node, selecteur)[0] || null;
  node.querySelectorAll = (selecteur) => chercher(node, selecteur);
  return node;
}

function correspond(node, selecteur) {
  if (selecteur === "i" || selecteur === "button" || selecteur === "p") {
    return node.tagName === selecteur.toUpperCase();
  }
  if (selecteur.startsWith("form[")) return node.tagName === "FORM" && correspond(node, selecteur.slice(4));
  if (selecteur.startsWith("[name=")) {
    const nom = selecteur.slice(7, -2);
    return node.name === nom || node.attrs.name === nom;
  }
  if (selecteur.startsWith("[") && selecteur.endsWith("]")) {
    return node.getAttribute(selecteur.slice(1, -1)) !== null;
  }
  return false;
}

function chercher(node, selecteur) {
  const trouves = [];
  (node.children || []).forEach((enfant) => {
    if (correspond(enfant, selecteur)) trouves.push(enfant);
    trouves.push(...chercher(enfant, selecteur));
  });
  return trouves;
}

function documentVocal() {
  const doc = creerElement("html");
  doc.documentElement = doc;
  doc.createElement = (tag) => {
    const element = creerElement(tag);
    element.ownerDocument = doc;
    return element;
  };
  const formulaire = creerElement("form");
  formulaire.ownerDocument = doc;
  formulaire.setAttribute("data-voice-fields", "email,password,first_name");
  let soumis = false;
  formulaire.addEventListener("submit", () => { soumis = true; });
  formulaire.aEteSoumis = () => soumis;

  function champ(type, nom, id, libelle) {
    const label = creerElement("label");
    label.textContent = libelle;
    const input = creerElement("input");
    input.ownerDocument = doc;
    input.type = type;
    input.name = nom;
    input.id = id;
    input.setAttribute("type", type);
    input.setAttribute("name", nom);
    input.setAttribute("id", id);
    input.labels = [label];
    const bloc = creerElement("div");
    bloc.appendChild(label);
    bloc.appendChild(input);
    formulaire.appendChild(bloc);
    return input;
  }

  const email = champ("email", "email", "id_email", "Adresse email *");
  const motDePasse = champ("password", "password", "id_password", "Mot de passe *");
  const prenom = champ("text", "first_name", "id_first_name", "Prénom");

  const select = creerElement("select");
  select.setAttribute("data-voice-lang", "true");
  select.options = [{ value: "fr-FR" }, { value: "ar-TN" }, { value: "en-US" }];
  select.value = "fr-FR";
  const controles = creerElement("div");
  controles.setAttribute("data-voice-controls", "true");
  controles.appendChild(select);
  const repli = creerElement("p");
  repli.setAttribute("data-voice-fallback", "true");
  repli.className = "d-none";
  doc.appendChild(controles);
  doc.appendChild(repli);
  doc.appendChild(formulaire);
  return { doc, email, motDePasse, prenom, select, controles, repli, formulaire };
}

class ReconnaissanceSimulee {
  static mode = "ok";
  start() {
    if (this.onstart) this.onstart();
    if (ReconnaissanceSimulee.mode === "ok") {
      this.onresult({
        resultIndex: 0,
        results: [{ isFinal: true, 0: { transcript: "Ines point Ben arobase pme point tn" } }],
      });
      if (this.onend) this.onend();
    } else if (ReconnaissanceSimulee.mode === "attente") {
      /* reste en écoute jusqu'à abort */
    } else {
      const code = ReconnaissanceSimulee.mode;
      if (this.onerror) this.onerror({ error: code });
      if (this.onend) this.onend();
    }
  }
  abort() {
    if (this.onerror) this.onerror({ error: "aborted" });
    if (this.onend) this.onend();
  }
}

const stockage = new Map();
global.window = {
  localStorage: {
    getItem: (cle) => (stockage.has(cle) ? stockage.get(cle) : null),
    setItem: (cle, valeur) => stockage.set(cle, String(valeur)),
  },
  SpeechRecognition: ReconnaissanceSimulee,
};
global.CSS = { escape: (valeur) => valeur };

const page = documentVocal();
const montage = voice.monter(page.doc);
assert.equal(montage.actif, true);
assert.equal(page.repli.classList.contains("d-none"), true);
const boutonMdp = page.motDePasse.parentNode.querySelector("button");
assert.equal(boutonMdp.type, "button");
boutonMdp.listeners.click[0]();
assert.equal(page.motDePasse.value, "Ines point Ben arobase pme point tn");
assert.equal(page.motDePasse.type, "text");
const statutMdp = page.motDePasse.parentNode.parentNode.querySelector("p");
assert.equal(statutMdp.textContent, "Mot de passe affiché. Vérifiez-le avant d'envoyer.");
const oeil = page.motDePasse.parentNode.querySelector("[data-voice-reveal]");
assert.equal(oeil.getAttribute("aria-pressed"), "true");
oeil.listeners.click[0]();
assert.equal(page.motDePasse.type, "password");
oeil.listeners.click[0]();
assert.equal(page.motDePasse.type, "text");
assert.equal(page.formulaire.aEteSoumis(), false);

const boutonEmail = page.email.parentNode.querySelector("button");
assert.equal(boutonEmail.type, "button");
assert.equal(boutonEmail.getAttribute("aria-label"), "Dicter le champ Adresse email");
boutonEmail.listeners.click[0]();
assert.equal(page.email.value, "ines.ben@pme.tn");
const statutEmail = page.email.parentNode.parentNode.querySelector("p");
assert.equal(statutEmail.textContent, "Texte reconnu");
assert.equal(page.formulaire.aEteSoumis(), false);

ReconnaissanceSimulee.mode = "not-allowed";
boutonEmail.listeners.click[0]();
assert.match(statutEmail.textContent, /microphone refusé/i);
assert.equal(page.formulaire.aEteSoumis(), false);

page.select.value = "ar-TN";
ReconnaissanceSimulee.mode = "language-not-supported";
const boutonPrenom = page.prenom.parentNode.querySelector("button");
boutonPrenom.listeners.click[0]();
const statutPrenom = page.prenom.parentNode.parentNode.querySelector("p");
assert.match(statutPrenom.textContent, /arabe tunisien/i);
assert.equal(page.prenom.value, "");

ReconnaissanceSimulee.mode = "attente";
boutonPrenom.listeners.click[0]();
assert.equal(boutonPrenom.classList.contains("is-listening"), true);
assert.equal(statutPrenom.textContent, "Parlez maintenant...");
page.doc.listeners.keydown[0]({ key: "Escape" });
assert.match(statutPrenom.textContent, /Écoute interrompue/);
assert.equal(boutonPrenom.classList.contains("is-listening"), false);

const sansMoteur = documentVocal();
delete global.window.SpeechRecognition;
delete global.window.webkitSpeechRecognition;
const inactif = voice.monter(sansMoteur.doc);
assert.equal(inactif.actif, false);
assert.equal(sansMoteur.repli.classList.contains("d-none"), false);
assert.equal(sansMoteur.controles.classList.contains("d-none"), true);
assert.equal(sansMoteur.email.parentNode.querySelector("button"), null);

console.log("voice_input: transcription, sécurité et erreurs OK");
