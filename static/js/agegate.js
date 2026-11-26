// Altersabfrage: Westbummeln ist nur für Erwachsene. Das Skript steht direkt hinter dem Abfragefenster
// in index.html und läuft, bevor der Rest der Seite gezeichnet wird. Die Antwort „Ja“ merkt sich nur der
// Browser (localStorage), der Server speichert nichts davon.
(() => {
  const KEY = 'wb_age_confirmed';
  const gate = document.getElementById('ageGate');
  const root = document.documentElement;
  let confirmed = false;
  try { confirmed = localStorage.getItem(KEY) === '1'; } catch { /* Speicher gesperrt: jedes Mal fragen */ }
  if (confirmed) {
    gate.remove();
    return;
  }
  root.classList.add('ageGated');
  document.getElementById('ageYes').addEventListener('click', () => {
    try { localStorage.setItem(KEY, '1'); } catch { /* dann eben beim nächsten Mal wieder */ }
    root.classList.remove('ageGated');
    gate.remove();
  });
  document.getElementById('ageNo').addEventListener('click', () => {
    location.replace('https://www.google.com/');
  });
  document.getElementById('ageYes').focus();
})();
