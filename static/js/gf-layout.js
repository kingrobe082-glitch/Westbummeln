// GF-Ansicht: Sobald man ein Fahrzeug führt, klappt „Fahrzeuge übernehmen“ zu einer
// schmalen Leiste zusammen und das eigene Fahrzeug rückt neben die Karte.
// Ob die Liste offen ist, merkt sich nur dieser Browser (localStorage).
(function () {
  const KEY = 'wb.fahrzeugliste.offen';
  const el = id => document.getElementById(id);
  let open = false;
  let active = false;
  try { open = localStorage.getItem(KEY) === '1'; } catch { /* Speicher gesperrt: eingeklappt starten */ }

  function sync() {
    el('vehiclesPanel').classList.toggle('open', open);
    el('vehiclesToggle').setAttribute('aria-expanded', String(open));
  }

  function setOpen(value) {
    open = value;
    try { localStorage.setItem(KEY, open ? '1' : '0'); } catch { /* dann nur bis zum Neuladen */ }
    sync();
  }

  el('vehiclesToggle').addEventListener('click', () => setOpen(!open));
  el('gfRelease').addEventListener('click', () => send('release'));
  sync();

  window.WBLayout = {
    // Wird bei jedem render() aufgerufen: nur Klassen und Texte setzen, nichts neu aufbauen,
    // damit Auf/Zu-Zustand und Scrollpositionen erhalten bleiben.
    apply(mine, labels) {
      const next = Boolean(mine);
      if (next !== active) {
        active = next;
        document.body.classList.toggle('gf-mode', active);
      }
      if (!mine) return;
      el('gfVehicle').textContent = mine.call;
      el('gfStatus').textContent = 'Status ' + mine.status + ' · ' + (labels[mine.status] || '');
      const atStation = mine.phase === 'wache';
      el('gfRelease').disabled = !atStation;
      el('gfRelease').title = atStation ? '' : 'Aussteigen geht nur auf der Wache';
    },
    // „In Liste zeigen“ auf der Karte: eingeklappte Liste dafür aufklappen.
    openList() {
      if (active && !open) setOpen(true);
    },
  };
})();
