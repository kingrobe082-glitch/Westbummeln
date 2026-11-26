// Progressive Web App: Service Worker registrieren, Update-Hinweis, „App installieren“-Knopf.
// Eigene Datei, weil die CSP keine Inline-Skripte erlaubt.
(() => {
  'use strict';

  const offlinePage = document.body.dataset.offlinePage === '1'; // Skript läuft mit defer, body steht schon

  function bar(text, buttonText, onClick) {
    const box = document.createElement('div');
    box.className = 'pwaBar';
    box.setAttribute('role', 'status');
    const label = document.createElement('span');
    label.textContent = text;
    box.append(label);
    if (buttonText) {
      const button = document.createElement('button');
      button.type = 'button';
      button.textContent = buttonText;
      button.addEventListener('click', onClick);
      box.append(button);
    }
    const close = document.createElement('button');
    close.type = 'button';
    close.className = 'pwaClose';
    close.setAttribute('aria-label', 'Hinweis schließen');
    close.textContent = '✕';
    close.addEventListener('click', () => box.remove());
    box.append(close);
    document.body.append(box);
    return box;
  }

  // ---------------------------------------------------------------- Service Worker
  if ('serviceWorker' in navigator) {
    // Wurde die Seite schon von einem Worker gesteuert, ist ein Wechsel ein Update (sonst Erstinstallation).
    const hadController = Boolean(navigator.serviceWorker.controller);
    let hinted = false;
    navigator.serviceWorker.addEventListener('controllerchange', () => {
      if (!hadController || hinted || offlinePage) return;
      hinted = true;
      bar('Neue Version von Westbummeln ist da – sie lädt beim nächsten Start automatisch.',
        'Jetzt neu laden', () => window.location.reload());
    });

    window.addEventListener('load', () => {
      navigator.serviceWorker.register('/sw.js', { scope: '/', updateViaCache: 'none' }).then(registration => {
        // Lange Spielrunden laden die Seite nie neu: deshalb zwischendurch nach Updates fragen.
        setInterval(() => registration.update().catch(() => {}), 30 * 60 * 1000);
      }).catch(error => console.warn('Service Worker nicht registriert:', error));
    });
  }

  // Offline-Seite: sobald das Netz zurück ist, die eigentliche Seite neu laden.
  if (offlinePage) {
    window.addEventListener('online', () => window.location.reload());
    return;
  }

  // ---------------------------------------------------------------- Installieren
  let installEvent = null;
  let installButton = null;

  function hideInstall() {
    installEvent = null;
    installButton?.remove();
    installButton = null;
  }

  window.addEventListener('beforeinstallprompt', event => {
    event.preventDefault(); // eigenen Knopf zeigen statt der Browser-Leiste
    installEvent = event;
    if (installButton) return;
    const login = document.getElementById('login');
    if (!login) return;
    installButton = document.createElement('button');
    installButton.type = 'button';
    installButton.id = 'installApp';
    installButton.className = 'pwaInstall';
    installButton.textContent = '📲 App installieren';
    installButton.addEventListener('click', async () => {
      if (!installEvent) return;
      const prompt = installEvent;
      installEvent = null;
      prompt.prompt();
      const choice = await prompt.userChoice.catch(() => null);
      if (choice?.outcome === 'accepted') hideInstall();
    });
    login.append(installButton);
  });

  window.addEventListener('appinstalled', hideInstall);
})();
