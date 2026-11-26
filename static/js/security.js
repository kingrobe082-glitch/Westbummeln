// Kontosicherheit: Passwort ändern und auf allen Geräten abmelden.
async function securityAction(action, fields = {}) {
  const response = await fetch('/account', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken() },
    body: JSON.stringify({ action, ...fields })
  });
  let data = {};
  try { data = await response.json(); } catch { /* keine JSON-Antwort */ }
  if (!response.ok) throw new Error(data.error || 'Serverfehler (' + response.status + '). Bitte versuche es gleich noch einmal.');
  return data;
}

$('passwordForm').addEventListener('submit', async event => {
  event.preventDefault();
  const oldPassword = $('oldPassword').value;
  const newPassword = $('newPassword').value;
  if (!oldPassword) return setNotice('Bitte gib dein bisheriges Passwort ein.', 'error');
  if (newPassword.length < 8) return setNotice('Das neue Passwort braucht mindestens 8 Zeichen.', 'error');
  const submit = $('passwordSubmit');
  submit.disabled = true;
  try {
    await securityAction('change_password', { old_password: oldPassword, new_password: newPassword });
    $('oldPassword').value = '';
    $('newPassword').value = '';
    $('securityPanel').open = false;
    setNotice('Passwort geändert. Alle anderen Geräte sind abgemeldet.', 'ok');
  } catch (error) {
    setNotice(error instanceof TypeError ? 'Keine Verbindung zum Server. Bitte versuche es noch einmal.' : error.message, 'error');
  } finally {
    submit.disabled = false;
  }
});

$('logoutAll').onclick = async () => {
  if (!confirm('Wirklich auf allen Geräten abmelden, auch auf diesem?')) return;
  try {
    await securityAction('logout_all');
    showAccount({});
    await loadAccount();
    setNotice('Du bist jetzt auf allen Geräten abgemeldet.', 'ok');
  } catch (error) {
    setNotice(error instanceof TypeError ? 'Keine Verbindung zum Server. Bitte versuche es noch einmal.' : error.message, 'error');
  }
};
