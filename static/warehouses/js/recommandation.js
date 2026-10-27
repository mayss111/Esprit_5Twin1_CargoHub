/*
 * Tant que Celery classe les entrepôts, on interroge le serveur.
 * Dès que le résultat est prêt, on ouvre la page qui l'affiche.
 */
(() => {
  const zone = document.getElementById("recommandation-attente");
  if (!zone) return;
  const message = zone.querySelector("[data-message]");
  let essais = 0;

  const interroger = async () => {
    essais += 1;
    try {
      const reponse = await fetch(zone.dataset.statutUrl, { headers: { Accept: "application/json" } });
      const data = await reponse.json();
      if (data.statut === "PRET" || data.statut === "ERREUR") {
        window.location.href = zone.dataset.resultatUrl;
        return;
      }
    } catch (erreur) {
      // erreur réseau passagère : on réessaie au prochain tour
    }
    if (essais >= 150) {
      message.textContent = zone.dataset.timeout;
      return;
    }
    setTimeout(interroger, 2000);
  };
  setTimeout(interroger, 2000);
})();
