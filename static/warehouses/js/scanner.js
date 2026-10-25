(function () {
  const bouton = document.getElementById("ouvrir-camera");
  const zone = document.getElementById("lecteur");
  const champ = document.getElementById("jeton");
  const formulaire = document.getElementById("form-identifier");
  const message = document.getElementById("camera-message");
  if (!bouton || typeof Html5Qrcode === "undefined") return;
  let scanner = null;
  bouton.addEventListener("click", function () {
    if (!scanner) scanner = new Html5Qrcode("lecteur");
    bouton.disabled = true;
    scanner
      .start(
        { facingMode: "environment" },
        { fps: 8, qrbox: 220 },
        function (texte) {
          champ.value = texte;
          scanner.stop().finally(function () {
            bouton.disabled = false;
            if (message) message.textContent = "QR Code lu. Vérifiez-le, puis confirmez l'opération.";
            formulaire.requestSubmit();
          });
        },
        function () {}
      )
      .catch(function () {
        bouton.disabled = false;
        if (message) message.textContent = "Caméra indisponible. Collez le lien du QR Code.";
      });
  });
  zone.setAttribute("aria-label", "Lecteur de QR Code");
})();
