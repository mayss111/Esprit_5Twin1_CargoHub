(function () {
  var DELAI_MS = 300;

  function memoriserFocus(champ) {
    if (!champ || !champ.id) return;
    var info = { id: champ.id };
    if (typeof champ.selectionStart === "number") {
      info.debut = champ.selectionStart;
      info.fin = champ.selectionEnd;
    }
    sessionStorage.setItem("cargohub-filtre-focus", JSON.stringify(info));
  }

  function restaurerFocus() {
    var brut = sessionStorage.getItem("cargohub-filtre-focus");
    if (!brut) return;
    sessionStorage.removeItem("cargohub-filtre-focus");
    var info;
    try {
      info = JSON.parse(brut);
    } catch (erreur) {
      return;
    }
    var champ = document.getElementById(info.id);
    if (!champ) return;
    champ.focus();
    if (typeof info.debut === "number" && champ.setSelectionRange) {
      try {
        champ.setSelectionRange(info.debut, info.fin);
      } catch (erreur) {
        /* Certains navigateurs refusent le curseur sur un champ date. */
      }
    }
  }

  document.querySelectorAll("form[data-filtre-auto]").forEach(function (form) {
    var attente = null;
    var signature = new URLSearchParams(new FormData(form)).toString();

    function appliquer() {
      var courant = new URLSearchParams(new FormData(form)).toString();
      if (courant === signature) return;
      memoriserFocus(document.activeElement);
      form.submit();
    }

    form.addEventListener("input", function (event) {
      var champ = event.target;
      if (!champ || !champ.name || event.isComposing) return;
      if (champ.tagName === "SELECT" || champ.type === "date") return;
      window.clearTimeout(attente);
      attente = window.setTimeout(appliquer, DELAI_MS);
    });

    form.addEventListener("change", function (event) {
      var champ = event.target;
      if (!champ || !champ.name) return;
      if (champ.tagName === "SELECT" || champ.type === "date") appliquer();
    });
  });

  restaurerFocus();
})();
