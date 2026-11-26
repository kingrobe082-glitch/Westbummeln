let accountBusy = false;
let developerAccount = false;
let publicRoomCode = '';
function showAccount({ name, developer, staff, hasPassword }) {
  developerAccount = Boolean(developer);
  $('moderationLink').classList.toggle('hidden', !staff);
  $('passwordForm').classList.toggle('hidden', !hasPassword);
  if (!name) $('securityPanel').open = false;
  $('accountControls').classList.toggle('hidden', Boolean(name));
  $('accountSession').classList.toggle('hidden', !name);
  $('signedInAs').textContent = name ? 'Angemeldet als ' + name : '';
  $('roomEntry').classList.toggle('hidden', !name);
  $('join').disabled = !name;
  $('createRoom').disabled = !name;
  $('publicRoomRow').classList.toggle('hidden', !publicRoomCode);
  $('publicRoom').disabled = !name;
  $('developerPanel').classList.toggle('hidden', !developer);
  if (!developer) {
    $('developerPanel').open = false;
    $('developerStatus').textContent = '';
  }
  if (typeof updatePrivacyPanel === 'function') updatePrivacyPanel({ name, hasPassword });
}

let authMode = 'login';
function setNotice(text, kind) {
  const n = $('accountNotice');
  n.textContent = text || '';
  n.className = 'small notice' + (kind ? ' ' + kind : '') + (text ? '' : ' hidden');
}
function setAuthMode(mode) {
  authMode = mode;
  $('tabLogin').classList.toggle('active', mode === 'login');
  $('tabRegister').classList.toggle('active', mode === 'register');
  $('registerHint').classList.toggle('hidden', mode !== 'register');
  $('nameLabel').textContent = mode === 'register' ? 'Benutzername (3–24 Zeichen)' : 'Benutzername oder E-Mail';
  $('accountPassword').autocomplete = mode === 'register' ? 'new-password' : 'current-password';
  $('accountSubmit').textContent = mode === 'register' ? 'Konto erstellen' : 'Anmelden';
  setNotice('');
}

async function accountAction(action, fields = {}) {
  if (accountBusy) return;
  accountBusy = true;
  const submit = $('accountSubmit');
  const label = submit.textContent;
  submit.disabled = true;
  if (action === 'login' || action === 'register') {
    submit.textContent = 'Bitte warten …';
    setNotice('Einen Moment, der Server prüft deine Daten. Das kann beim ersten Mal bis zu einer Minute dauern.', 'info');
  }
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 60000);
  try {
    const response = await fetch('/account', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken() },
      body: JSON.stringify({ action, ...fields }),
      signal: controller.signal
    });
    let account = {};
    try { account = await response.json(); } catch { /* keine JSON-Antwort */ }
    if (!response.ok) throw new Error(account.error || 'Serverfehler (' + response.status + '). Bitte versuche es gleich noch einmal.');
    $('accountPassword').value = '';
    if (action === 'logout') showAccount({});
    await loadAccount();
    setNotice(action === 'register' ? 'Konto erstellt. Du bist angemeldet.' : '', action === 'register' ? 'ok' : '');
  } catch (error) {
    const message = error.name === 'AbortError'
      ? 'Der Server antwortet nicht. Er wacht vielleicht gerade auf. Versuche es in einer Minute noch einmal.'
      : error instanceof TypeError ? 'Keine Verbindung zum Server. Prüfe dein Internet und versuche es noch einmal.' : error.message;
    setNotice(message, 'error');
  } finally {
    clearTimeout(timer);
    accountBusy = false;
    submit.disabled = false;
    submit.textContent = label;
  }
}

async function loadAccount() {
  const response = await fetch('/account');
  if (!response.ok) throw new Error('Kontodienst gerade nicht erreichbar.');
  const account = await response.json();
  publicRoomCode = account.publicRoom || '';
  $('publicRoomCode').textContent = publicRoomCode;
  showAccount(account);
  if (account.loginNotice) setNotice(account.loginNotice, 'error');
  $('discordLogin').classList.toggle('hidden', !account.discordLogin || Boolean(account.name));
  const voiceLink = $('discordVoice');
  voiceLink.classList.toggle('hidden', !account.discordVoiceUrl);
  if (account.discordVoiceUrl) voiceLink.href = account.discordVoiceUrl;
  if (account.name || !account.googleClientId) return;

  const renderGoogleButton = () => {
    const google = window.google.accounts.id;
    google.initialize({
      client_id: account.googleClientId,
      nonce: account.nonce,
      callback: ({ credential }) => accountAction('google', { credential })
    });
    $('googleButton').replaceChildren();
    google.renderButton($('googleButton'), { theme: 'outline', size: 'large', locale: 'de' });
  };
  if (window.google?.accounts?.id) {
    renderGoogleButton();
  } else {
    const script = document.createElement('script');
    script.src = 'https://accounts.google.com/gsi/client';
    script.async = true;
    script.onload = renderGoogleButton;
    script.onerror = () => setNotice('Google-Anmeldung konnte nicht geladen werden.', 'error');
    document.head.append(script);
  }
}

$('tabLogin').onclick = () => setAuthMode('login');
$('tabRegister').onclick = () => setAuthMode('register');
$('accountForm').addEventListener('submit', event => {
  event.preventDefault();
  const name = $('accountName').value.trim();
  const password = $('accountPassword').value;
  if (!name) return setNotice(authMode === 'register' ? 'Bitte gib einen Benutzernamen ein.' : 'Bitte gib Benutzername oder E-Mail ein.', 'error');
  if (authMode === 'register') {
    if (!/^[\p{L}\p{N}_-]{3,24}$/u.test(name)) return setNotice('Benutzername: 3–24 Buchstaben, Zahlen, Unterstriche oder Bindestriche, ohne Leerzeichen.', 'error');
    if (password.length < 8) return setNotice('Das Passwort braucht mindestens 8 Zeichen.', 'error');
  } else if (!password) {
    return setNotice('Bitte gib dein Passwort ein.', 'error');
  }
  accountAction(authMode, authMode === 'register' ? { name, password } : { name, password });
});
$('accountLogout').onclick = () => accountAction('logout');
$('developerRefresh').onclick = async () => {
  const status = $('developerStatus');
  try {
    const response = await fetch('/developer');
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Serverstatus gerade nicht verfügbar.');
    status.textContent = data.rooms + ' aktive Räume · ' + data.players + ' aktive Spieler · '
      + data.rooms_total + ' Räume insgesamt';
  } catch (error) {
    status.textContent = error.message;
  }
};
$('radioFilter').onchange = () => { if (state) render(); };
const loginErrors = {
  cancel: 'Discord-Anmeldung abgebrochen.',
  state: 'Die Discord-Anmeldung ist abgelaufen. Bitte versuche es noch einmal.',
  guild: 'Du musst Mitglied auf dem Discord-Server sein, um dich anzumelden.',
  off: 'Die Discord-Anmeldung ist nicht eingerichtet.',
  failed: 'Discord-Anmeldung fehlgeschlagen. Bitte versuche es noch einmal.',
  banned: 'Dein Konto ist gesperrt.'
};
const loginError = new URLSearchParams(location.search).get('login_error');
if (loginError) {
  history.replaceState(null, '', '/');
  setNotice(loginErrors[loginError] || loginErrors.failed, 'error');
}
loadAccount().catch(error => setNotice(error.message, 'error'));

if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/sw.js').catch(error => console.warn('App-Registrierung fehlgeschlagen', error));
}
