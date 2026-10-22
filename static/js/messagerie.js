/*
 * Messagerie CargoHub — affiche en direct les messages des autres participants (WebSocket).
 * L'envoi passe par le formulaire classique : la page marche aussi sans WebSocket.
 */
(() => {
  const fil = document.getElementById("fil");
  if (!fil || !("WebSocket" in window)) return;

  const protocole = location.protocol === "https:" ? "wss" : "ws";
  const socket = new WebSocket(`${protocole}://${location.host}/ws/messagerie/${fil.dataset.conversation}/`);

  socket.addEventListener("message", (event) => {
    const data = JSON.parse(event.data);
    if (String(data.auteur_id) === fil.dataset.moi) return; // mes messages s'affichent au rechargement
    fil.querySelector("[data-vide]")?.remove();

    const item = document.createElement("li");
    item.className = "chat-message";
    const entete = document.createElement("div");
    entete.className = "small text-muted";
    entete.textContent = `${data.auteur} · ${data.date || ""}`;
    const bulle = document.createElement("div");
    bulle.className = "chat-bulle";
    bulle.textContent = data.message; // textContent : aucun HTML injecté
    item.append(entete, bulle);
    fil.append(item);
    item.scrollIntoView({ behavior: "smooth", block: "nearest" });
  });
})();
