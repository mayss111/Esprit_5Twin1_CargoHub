/*
 * Messagerie CargoHub - Version simplifiée et robuste
 */

// =========================================================================
// ENREGISTREMENT VOCAL SIMPLIFIÉ
// =========================================================================
(function() {
  'use strict';

  const btnEnregistrer = document.getElementById('btn-enregistrer-vocal');
  const statutVocal = document.getElementById('statut-vocal');
  const containerAudio = document.getElementById('container-audio');
  const inputAudio = document.getElementById('id_fichier_audio');
  const annonce = document.getElementById('messagerie-annonce');

  let mediaRecorder = null;
  let audioChunks = [];

  if (!btnEnregistrer) {
    console.log('Bouton enregistrer non trouvé');
    return;
  }

  btnEnregistrer.addEventListener('click', async function() {
    // Si enregistrement en cours, l'arrêter
    if (mediaRecorder && mediaRecorder.state === 'recording') {
      mediaRecorder.stop();
      return;
    }

    // Vérifier support
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      alert('Votre navigateur ne supporte pas l\'enregistrement audio. Utilisez Chrome, Firefox ou Edge.');
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      audioChunks = [];

      mediaRecorder = new MediaRecorder(stream);

      mediaRecorder.ondataavailable = function(event) {
        if (event.data.size > 0) {
          audioChunks.push(event.data);
        }
      };

      mediaRecorder.onstop = function() {
        const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
        const audioFile = new File([audioBlob], 'vocal.webm', { type: 'audio/webm' });

        // Créer un DataTransfer et remplir l'input
        const dataTransfer = new DataTransfer();
        dataTransfer.items.add(audioFile);
        inputAudio.files = dataTransfer.files;

        // Afficher le container audio
        containerAudio.style.display = 'block';

        // Mettre à jour UI
        btnEnregistrer.innerHTML = '<i class="bi bi-mic-fill"></i> Réenregistrer';
        statutVocal.textContent = 'Vocal enregistré. Cliquez sur Envoyer.';

        // Arrêter le stream
        stream.getTracks().forEach(track => track.stop());
      };

      mediaRecorder.start();
      btnEnregistrer.innerHTML = '<i class="bi bi-stop-circle-fill"></i> Arrêter';
      statutVocal.textContent = 'Enregistrement en cours...';

    } catch (error) {
      console.error('Erreur enregistrement:', error);
      alert('Erreur: ' + error.message + '. Veuillez autoriser l\'accès au microphone.');
    }
  });
})();

// =========================================================================
// BOUTON ÉCOUTER (TTS) - Version ultra simple
// =========================================================================
(function() {
  'use strict';

  if (!('speechSynthesis' in window)) {
    console.log('SpeechSynthesis non disponible');
    return;
  }

  document.addEventListener('click', function(event) {
    const bouton = event.target.closest('[data-tts-text]');
    if (!bouton) return;

    event.preventDefault();

    const texte = bouton.getAttribute('data-tts-text');
    if (!texte || texte === 'Message vocal CargoHub.') {
      return; // Pas de texte à lire
    }

    console.log('Lecture:', texte.substring(0, 50));

    // Annuler toute lecture en cours
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

    utterance.onerror = function(error) {
      console.error('Erreur TTS:', error);
      bouton.innerHTML = '<i class="bi bi-volume-up"></i> Écouter';
    };

    window.speechSynthesis.speak(utterance);
  });
})();

// =========================================================================
// WEBSOCKET (optionnel)
// =========================================================================
(function() {
  'use strict';

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
      divBulle.textContent = data.message;

      li.appendChild(divAuteur);
      li.appendChild(divBulle);
      fil.appendChild(li);

      li.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    } catch (e) {
      console.error('Erreur WebSocket:', e);
    }
  };
})();
