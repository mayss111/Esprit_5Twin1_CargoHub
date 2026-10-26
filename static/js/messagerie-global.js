/* Mise à jour temps réel de l'icône et de la fenêtre Messagerie CargoHub. */
(() => {
  const indicateur = document.querySelector("[data-messagerie-notifications]");
  const menu = document.getElementById("messagerie-menu");
  if (!indicateur || !menu || !("WebSocket" in window)) return;

  const protocole = location.protocol === "https:" ? "wss" : "ws";
  const socket = new WebSocket(`${protocole}://${location.host}/ws/messagerie/notifications/`);

  socket.addEventListener("message", (event) => {
    const data = JSON.parse(event.data);
    let badge = indicateur.querySelector("[data-messagerie-badge]");
    const total = Number(badge?.textContent || 0) + 1;
    if (!badge) {
      badge = document.createElement("span");
      badge.className = "badge rounded-pill text-bg-warning";
      badge.dataset.messagerieBadge = "";
      indicateur.append(" ", badge);
    }
    badge.textContent = total;
    indicateur.setAttribute("aria-label", `Messagerie, ${total} message${total > 1 ? "s" : ""} non lu${total > 1 ? "s" : ""}`);

    menu.querySelector("[data-messagerie-vide]")?.remove();
    const item = document.createElement("li");
    const lien = document.createElement("a");
    lien.className = "dropdown-item fw-semibold";
    lien.href = data.lien;
    const auteur = document.createElement("span");
    auteur.className = "d-block";
    auteur.textContent = data.auteur || "Nouveau message";
    const apercu = document.createElement("small");
    apercu.className = "text-muted";
    apercu.textContent = data.message || "Vous avez reçu un nouveau message.";
    lien.append(auteur, apercu);
    item.append(lien);
    menu.insertBefore(item, menu.querySelector("hr")?.parentElement || menu.children[1]);

    const toast = document.createElement("div");
    toast.className = "messagerie-toast shadow";
    toast.setAttribute("role", "status");
    toast.setAttribute("aria-live", "polite");
    toast.setAttribute("aria-atomic", "true");
    toast.innerHTML = '<i class="bi bi-chat-dots-fill me-2" aria-hidden="true"></i><strong>Nouveau message</strong>';
    toast.append(document.createTextNode(` de ${data.auteur || "un interlocuteur"}`));
    document.body.append(toast);
    window.setTimeout(() => toast.remove(), 5000);
  });
})();
