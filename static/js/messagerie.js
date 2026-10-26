/*
 * Messagerie CargoHub - lecture, enregistrement et envoi des vocaux
 */

// =========================================================================
// ENREGISTREUR VOCAL
// =========================================================================
(function() {
  const formulaire = document.querySelector('form[data-envoi-message]');
  const bouton = document.querySelector('[data-enregistrer-vocal]');
  const statut = document.querySelector('[data-statut-vocal]');
  const apercu = document.querySelector('[data-apercu-vocal]');
  const audioApercu = document.querySelector('[data-audio-apercu]');
  const dureeApercu = document.querySelector('[data-duree-vocal]');
  const boutonSupprimer = document.querySelector('[data-supprimer-vocal]');
  const boutonEnvoyer = document.querySelector('[data-envoyer-vocal]');
  if (!formulaire || !bouton || !statut) return;

  let enregistreur = null;
  let flux = null;
  let morceaux = [];
  let vocalPrepare = null;
  let urlApercu = null;
  let envoiEnCours = false;

  function annoncer(message, erreur) {
    statut.textContent = message;
    statut.classList.toggle('text-danger', Boolean(erreur));
    statut.classList.toggle('text-success', !erreur && message.includes('envoyé'));
  }

  if (audioApercu && dureeApercu) audioApercu.addEventListener('loadedmetadata', function() {
    const secondes = Math.round(audioApercu.duration || 0);
    const minutes = Math.floor(secondes / 60);
    const reste = String(secondes % 60).padStart(2, '0');
    dureeApercu.textContent = `Durée : ${minutes}:${reste}`;
  });

  function mimeAudio() {
    const types = ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus', 'audio/ogg'];
    return types.find(type => window.MediaRecorder && MediaRecorder.isTypeSupported(type)) || '';
  }

  function arreterFlux() {
    if (flux) flux.getTracks().forEach(track => track.stop());
    flux = null;
  }

  function afficherApercu(blob) {
    vocalPrepare = new File([blob], `message-vocal-${Date.now()}.${blob.type.includes('ogg') ? 'ogg' : 'webm'}`, {
      type: blob.type || 'audio/webm'
    });
    if (urlApercu) URL.revokeObjectURL(urlApercu);
    urlApercu = URL.createObjectURL(vocalPrepare);
    if (audioApercu) audioApercu.src = urlApercu;
    if (dureeApercu) dureeApercu.textContent = 'Durée : calcul en cours…';
    if (apercu) apercu.classList.remove('d-none');
    bouton.innerHTML = '<i class="bi bi-mic" aria-hidden="true"></i> Réenregistrer';
    bouton.disabled = false;
    bouton.classList.remove('btn-danger');
    bouton.classList.add('btn-outline-danger');
    annoncer('Aperçu prêt. Écoutez, supprimez ou envoyez le vocal.');
  }

  function supprimerVocal() {
    vocalPrepare = null;
    if (urlApercu) URL.revokeObjectURL(urlApercu);
    urlApercu = null;
    if (audioApercu) {
      audioApercu.pause();
      audioApercu.removeAttribute('src');
      audioApercu.load();
    }
    if (apercu) apercu.classList.add('d-none');
    bouton.disabled = false;
    bouton.innerHTML = '<i class="bi bi-mic" aria-hidden="true"></i> Enregistrer un vocal';
    bouton.classList.remove('btn-danger');
    bouton.classList.add('btn-outline-danger');
    annoncer('Vocal supprimé. Cliquez pour recommencer.');
  }

  function envoyerVocal(fichier) {
    const inputAudio = formulaire.querySelector('input[name="fichier_audio"]');
    if (!fichier || !inputAudio || !window.DataTransfer) {
      annoncer('Votre navigateur ne permet pas l’envoi direct du vocal.', true);
      return;
    }

    // Réutiliser la soumission multipart native garantit que Django reçoit
    // le token CSRF et le fichier exactement comme un formulaire classique.
    const donneesFichier = new DataTransfer();
    donneesFichier.items.add(fichier);
    inputAudio.files = donneesFichier.files;

    // Un envoi vocal ne doit pas embarquer le texte ou une pièce jointe
    // éventuellement restés dans le formulaire.
    const contenu = formulaire.querySelector('[name="contenu"]');
    const pieceJointe = formulaire.querySelector('[name="piece_jointe"]');
    if (contenu) contenu.value = '';
    if (pieceJointe) pieceJointe.value = '';

    const donnees = new FormData(formulaire);
    // Garantit que le Blob MediaRecorder est bien transmis, même lorsque le
    // navigateur ne répercute pas input.files dans FormData(formulaire).
    donnees.set('fichier_audio', fichier, fichier.name);
    const csrf = donnees.get('csrfmiddlewaretoken');

    envoiEnCours = true;
    bouton.disabled = true;
    annoncer('Envoi du message vocal…');
    fetch(formulaire.action || window.location.href, {
      method: 'POST',
      body: donnees,
      credentials: 'same-origin',
      headers: {
        'X-Requested-With': 'XMLHttpRequest',
        'X-CSRFToken': csrf || ''
      }
    }).then(async response => {
      if (response.redirected) {
        window.location.reload();
        return;
      }
      if (!response.ok) {
        let details = `HTTP ${response.status}`;
        try {
          const payload = await response.json();
          details = Object.values(payload.errors || {}).flat().map(error => error.message || error).join(' ');
        } catch (ignore) {}
        throw new Error(details || 'Le serveur a refusé le vocal.');
      }
      const html = await response.text();
      const documentRetour = new DOMParser().parseFromString(html, 'text/html');
      const erreurs = documentRetour.querySelector('.errorlist');
      throw new Error(erreurs ? erreurs.textContent.trim() : 'Le serveur n’a pas accepté le vocal.');
    }).catch(erreur => {
      console.error('Envoi du vocal impossible:', erreur);
      annoncer(`Envoi refusé : ${erreur.message}`, true);
      bouton.disabled = false;
      envoiEnCours = false;
    });
  }

  bouton.addEventListener('click', async function() {
    if (envoiEnCours) return;

    if (enregistreur && enregistreur.state === 'recording') {
      enregistreur.stop();
      bouton.innerHTML = '<i class="bi bi-hourglass-split" aria-hidden="true"></i> Préparation…';
      bouton.disabled = true;
      annoncer('Préparation du message vocal…');
      return;
    }

    if (!window.isSecureContext && !['localhost', '127.0.0.1'].includes(location.hostname)) {
      annoncer('Le microphone exige HTTPS (ou localhost). Ouvrez CargoHub en HTTPS.', true);
      return;
    }
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia || !window.MediaRecorder) {
      annoncer('L’enregistrement vocal n’est pas pris en charge. Choisissez un fichier audio.', true);
      return;
    }

    try {
      flux = await navigator.mediaDevices.getUserMedia({audio: true});
      const type = mimeAudio();
      enregistreur = new MediaRecorder(flux, type ? {mimeType: type} : undefined);
      morceaux = [];
      enregistreur.addEventListener('dataavailable', event => {
        if (event.data && event.data.size) morceaux.push(event.data);
      });
      enregistreur.addEventListener('stop', () => {
        arreterFlux();
        const blob = new Blob(morceaux, {type: enregistreur.mimeType || 'audio/webm'});
        if (!blob.size) {
          bouton.disabled = false;
          bouton.innerHTML = '<i class="bi bi-mic" aria-hidden="true"></i> Enregistrer un vocal';
          annoncer('Aucun son enregistré. Réessayez.', true);
          return;
        }
        // Le vocal est envoyé au destinataire dès l'arrêt de l'enregistrement.
        envoyerVocal(new File([blob], `message-vocal-${Date.now()}.${blob.type.includes('ogg') ? 'ogg' : 'webm'}`, {
          type: blob.type || 'audio/webm'
        }));
      }, {once: true});
      enregistreur.start();
      bouton.innerHTML = '<i class="bi bi-stop-circle" aria-hidden="true"></i> Arrêter et envoyer';
      bouton.classList.replace('btn-outline-danger', 'btn-danger');
      annoncer('Enregistrement en cours…');
    } catch (erreur) {
      arreterFlux();
      console.error('Accès au microphone impossible:', erreur);
      annoncer('Microphone inaccessible. Autorisez-le ou choisissez un fichier audio.', true);
    }
  });

  if (boutonSupprimer) boutonSupprimer.addEventListener('click', supprimerVocal);
  if (boutonEnvoyer) boutonEnvoyer.addEventListener('click', function() {
    if (envoiEnCours || !vocalPrepare) return;
    envoyerVocal(vocalPrepare);
  });
})();

// =========================================================================
// BOUTON ÉCOUTER (TTS)
// =========================================================================
(function() {
  if (!('speechSynthesis' in window)) return;

  document.addEventListener('click', function(event) {
    const bouton = event.target.closest('[data-tts-text]');
    if (!bouton) return;

    event.preventDefault();
    const texte = bouton.getAttribute('data-tts-text');

    if (!texte || texte === 'Message vocal CargoHub.') return;

    window.speechSynthesis.cancel();

    const utterance = new SpeechSynthesisUtterance(texte);
    utterance.lang = 'fr-FR';
    utterance.rate = 1;

    utterance.onstart = function() {
      bouton.innerHTML = '<i class="bi bi-volume-down-fill"></i> Lecture...';
    };

    utterance.onend = function() {
      bouton.innerHTML = '<i class="bi bi-volume-up"></i> Écouter';
    };

    utterance.onerror = function() {
      bouton.innerHTML = '<i class="bi bi-volume-up"></i> Écouter';
    };

    window.speechSynthesis.speak(utterance);
  });
})();

// =========================================================================
// WEBSOCKET
// =========================================================================
(function() {
  const fil = document.getElementById('fil');
  if (!fil || !('WebSocket' in window)) return;

  const conversationId = fil.getAttribute('data-conversation');
  if (!conversationId) return;

  const protocole = location.protocol === 'https:' ? 'wss' : 'ws';
  const socket = new WebSocket(`${protocole}://${location.host}/ws/messagerie/${conversationId}/`);

  socket.onmessage = function(event) {
    try {
      const data = JSON.parse(event.data);
      const monId = fil.getAttribute('data-moi');

      if (String(data.auteur_id) === String(monId)) return;

      const vide = fil.querySelector('[data-vide]');
      if (vide) vide.remove();

      const li = document.createElement('li');
      li.className = 'chat-message';

      const divAuteur = document.createElement('div');
      divAuteur.className = 'small text-muted';
      divAuteur.textContent = `${data.auteur} · ${data.date || ''}`;

      const divBulle = document.createElement('div');
      divBulle.className = 'chat-bulle';
      if (data.message) divBulle.textContent = data.message;
      if (data.audio_url) {
        const audio = document.createElement('audio');
        audio.controls = true;
        audio.preload = 'metadata';
        audio.src = data.audio_url;
        audio.setAttribute('aria-label', 'Message vocal');
        divBulle.appendChild(audio);
      }

      if (!data.message && !data.audio_url) return;

      li.appendChild(divAuteur);
      li.appendChild(divBulle);
      fil.appendChild(li);

      li.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    } catch (e) {
      console.error('Erreur WebSocket:', e);
    }
  };
})();
