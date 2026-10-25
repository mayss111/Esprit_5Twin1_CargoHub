/*
 * IA du M4 — « Aide au choix ». Pendant que Celery calcule la recommandation, on interroge
 * le serveur toutes les 2 secondes ; dès que le résultat est prêt (ou en erreur), on recharge
 * la page qui affiche la carte. Le message d'attente est dans une zone aria-live.
 */
(() => {
  const carte = document.getElementById("aide-au-choix");
  if (!carte || carte.dataset.statut !== "EN_COURS") return;
  const message = carte.querySelector("[data-aide-message]");
  const MAX_ESSAIS = 45; // 1 min 30 s
  let essais = 0;

  const interroger = async () => {
    essais += 1;
    try {
      const reponse = await fetch(carte.dataset.statutUrl, { headers: { Accept: "application/json" } });
      const data = await reponse.json();
      if (data.statut !== "EN_COURS") {
        window.location.reload();
        return;
      }
    } catch (erreur) {
      // erreur réseau passagère : on réessaie au prochain tour
    }
    if (essais >= MAX_ESSAIS) {
      message.textContent = "L’analyse prend plus de temps que prévu. Rechargez la page dans un moment.";
      return;
    }
    setTimeout(interroger, 2000);
  };
  setTimeout(interroger, 2000);
})();
