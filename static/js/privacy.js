// Meine Daten: Datenexport und Konto löschen.
let deleteNeedsPassword = true;
let deleteUsername = '';

// Wird von showAccount (account.js) aufgerufen, sobald klar ist, wer angemeldet ist.
function updatePrivacyPanel({ name, hasPassword }) {
  deleteNeedsPassword = Boolean(hasPassword);
  deleteUsername = name || '';
  const input = $('deleteConfirm');
  input.value = '';
  input.type = deleteNeedsPassword ? 'password' : 'text';
  input.autocomplete = deleteNeedsPassword ? 'current-password' : 'off';
  input.maxLength = deleteNeedsPassword ? 128 : 24;
  $('deleteLabel').textContent = deleteNeedsPassword
    ? 'Passwort zur Bestätigung'
    : 'Zur Bestätigung deinen Benutzernamen eingeben: ' + deleteUsername;
  if (!name) $('privacyPanel').open = false;
}

function privacyError(error) {
  setNotice(error instanceof TypeError ? 'Keine Verbindung zum Server. Bitte versuche es noch einmal.' : error.message, 'error');
}

$('exportData').onclick = async () => {
  const button = $('exportData');
  button.disabled = true;
  try {
    const response = await fetch('/account/export');
    if (!response.ok) {
      let data = {};
      try { data = await response.json(); } catch { /* keine JSON-Antwort */ }
      throw new Error(data.error || 'Serverfehler (' + response.status + '). Bitte versuche es gleich noch einmal.');
    }
    const url = URL.createObjectURL(await response.blob());
    const link = document.createElement('a');
    link.href = url;
    link.download = 'westbummeln-meine-daten.json';
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    setNotice('Deine Daten wurden als Datei heruntergeladen.', 'ok');
  } catch (error) {
    privacyError(error);
  } finally {
    button.disabled = false;
  }
};

$('deleteForm').addEventListener('submit', async event => {
  event.preventDefault();
  const value = $('deleteConfirm').value;
  if (!value) return setNotice(deleteNeedsPassword ? 'Bitte gib dein Passwort ein.' : 'Bitte gib deinen Benutzernamen ein.', 'error');
  if (!confirm('Konto „' + deleteUsername + '“ wirklich endgültig löschen? Das lässt sich nicht rückgängig machen.')) return;
  const submit = $('deleteSubmit');
  submit.disabled = true;
  try {
    await securityAction('delete_account', deleteNeedsPassword ? { password: value } : { confirm: value });
    // Neu laden, damit kein Spielraum mehr offen ist. Die Meldung kommt über den Parameter.
    location.replace('/?konto_geloescht=1');
  } catch (error) {
    $('deleteConfirm').value = '';
    privacyError(error);
    submit.disabled = false;
  }
});

if (new URLSearchParams(location.search).has('konto_geloescht')) {
  history.replaceState(null, '', '/');
  setNotice('Dein Konto wurde gelöscht. Danke fürs Mitspielen!', 'ok');
}
