"""Discord-Anbindung für Westbummeln. Nur Standardbibliothek, kein Django-Import.

Die Hintergrund-Threads startet westbummeln/wsgi.py über game.rooms.start_background().

Drei voneinander unabhängige Funktionen, jede wird über Umgebungsvariablen eingeschaltet:

1. Anmeldung mit Discord (OAuth2)
   DISCORD_CLIENT_ID, DISCORD_CLIENT_SECRET
   optional DISCORD_GUILD_ID (nur Mitglieder dieses Servers dürfen sich anmelden),
            DISCORD_REDIRECT_URI (sonst wird sie aus der Serveradresse gebildet)

2. Funkprotokoll nach Discord (Webhook)
   DISCORD_WEBHOOK_URL
   optional DISCORD_ROOM (nur dieser Spielraum; ohne Angabe werden alle Räume mit [Raumcode] gespiegelt)

3. Discord-Kanal als Funk ins Spiel (ein Bot liest den Kanal mit)
   DISCORD_BOT_TOKEN, DISCORD_CHANNEL_ID und DISCORD_ROOM (der Spielraum, in dem die Nachrichten erscheinen)

Sonstiges: DISCORD_VOICE_URL (Einladungslink zum Discord-Sprachkanal, wird im Sprachfunk-Bereich angezeigt).
"""
import json
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import deque

API = os.environ.get('DISCORD_API', 'https://discord.com/api/v10').strip().rstrip('/')
AUTHORIZE_URL = os.environ.get('DISCORD_AUTHORIZE_URL', 'https://discord.com/oauth2/authorize').strip()
CLIENT_ID = os.environ.get('DISCORD_CLIENT_ID', '').strip()
CLIENT_SECRET = os.environ.get('DISCORD_CLIENT_SECRET', '').strip()
GUILD_ID = os.environ.get('DISCORD_GUILD_ID', '').strip()
REDIRECT_URI = os.environ.get('DISCORD_REDIRECT_URI', '').strip()
WEBHOOK_URL = os.environ.get('DISCORD_WEBHOOK_URL', '').strip()
BOT_TOKEN = os.environ.get('DISCORD_BOT_TOKEN', '').strip()
CHANNEL_ID = os.environ.get('DISCORD_CHANNEL_ID', '').strip()
ROOM = os.environ.get('DISCORD_ROOM', '').strip().upper()
VOICE_URL = os.environ.get('DISCORD_VOICE_URL', '').strip()
BATCH_SECONDS = float(os.environ.get('DISCORD_BATCH_SECONDS', '1.5'))
POLL_SECONDS = float(os.environ.get('DISCORD_POLL_SECONDS', '3'))

USER_AGENT = 'DiscordBot (https://github.com/westbummeln, 1.0)'
STATE_COOKIE = 'wb_discord_state'

_webhook_prefixes = ['https://discord.com/api/webhooks/', 'https://discordapp.com/api/webhooks/']
if os.environ.get('DISCORD_API'):
    _webhook_prefixes.append(API.rsplit('/', 1)[0] + '/webhooks/')
WEBHOOK_OK = any(WEBHOOK_URL.startswith(prefix) for prefix in _webhook_prefixes)
ROOM_OK = bool(re.fullmatch(r'[A-Z0-9-]{2,16}', ROOM))
BOT_OK = bool(BOT_TOKEN and re.fullmatch(r'\d{5,25}', CHANNEL_ID) and ROOM_OK)
VOICE_OK = VOICE_URL.startswith(('https://discord.gg/', 'https://discord.com/'))

_queue = deque(maxlen=300)
_wake = threading.Event()
_logged = {}


class LoginError(Exception):
    """code: 'failed' (technischer Fehler) oder 'guild' (kein Mitglied auf dem Discord-Server)."""

    def __init__(self, code):
        super().__init__(code)
        self.code = code


def _log_once(key, text, every=300):
    now = time.monotonic()
    if now - _logged.get(key, -every) >= every:
        _logged[key] = now
        print('Discord:', text, flush=True)


def _http(method, url, headers=None, form=None, body=None, timeout=15):
    data = None
    head = {'User-Agent': USER_AGENT, 'Accept': 'application/json', **(headers or {})}
    if form is not None:
        data = urllib.parse.urlencode(form).encode()
        head['Content-Type'] = 'application/x-www-form-urlencoded'
    elif body is not None:
        data = json.dumps(body).encode()
        head['Content-Type'] = 'application/json'
    request = urllib.request.Request(url, data=data, headers=head, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
            status = response.status
    except urllib.error.HTTPError as error:
        raw = error.read()
        status = error.code
    try:
        return status, (json.loads(raw) if raw else {})
    except ValueError:
        return status, {}


# ---------------------------------------------------------------- Anmeldung

def login_enabled():
    return bool(CLIENT_ID and CLIENT_SECRET)


def redirect_uri(host, secure):
    if REDIRECT_URI:
        return REDIRECT_URI
    base = os.environ.get('RENDER_EXTERNAL_URL', '').strip().rstrip('/')
    if base:
        return base + '/auth/discord/callback'
    return f"{'https' if secure else 'http'}://{host}/auth/discord/callback"


def authorize_url(state, redirect):
    query = {'client_id': CLIENT_ID, 'response_type': 'code', 'redirect_uri': redirect,
             'scope': 'identify guilds' if GUILD_ID else 'identify', 'state': state, 'prompt': 'none'}
    return AUTHORIZE_URL + '?' + urllib.parse.urlencode(query)


def complete_login(code, redirect):
    """Tauscht den Code gegen den Discord-Benutzer. Es wird nichts gespeichert außer der Discord-ID."""
    try:
        status, token = _http('POST', API + '/oauth2/token', form={
            'client_id': CLIENT_ID, 'client_secret': CLIENT_SECRET, 'grant_type': 'authorization_code',
            'code': code, 'redirect_uri': redirect})
        access = token.get('access_token') if status == 200 else None
        if not isinstance(access, str):
            _log_once('login', f'Anmeldung fehlgeschlagen (Token-Tausch Status {status}). '
                               'Client-Secret und Redirect-URL im Developer Portal prüfen.')
            raise LoginError('failed')
        auth = {'Authorization': 'Bearer ' + access}
        status, user = _http('GET', API + '/users/@me', headers=auth)
        if status != 200 or not str(user.get('id', '')).isdigit():
            raise LoginError('failed')
        if GUILD_ID:
            status, guilds = _http('GET', API + '/users/@me/guilds', headers=auth)
            if status != 200 or not isinstance(guilds, list):
                raise LoginError('failed')
            if not any(str(g.get('id')) == GUILD_ID for g in guilds if isinstance(g, dict)):
                raise LoginError('guild')
        return {'id': str(user['id']), 'username': str(user.get('username') or '')}
    except LoginError:
        raise
    except Exception as error:
        _log_once('login', f'Anmeldung fehlgeschlagen: {error}')
        raise LoginError('failed') from None


def public_config(logged_in):
    return {'discordLogin': login_enabled(), 'discordVoiceUrl': VOICE_URL if (VOICE_OK and logged_in) else ''}


# ---------------------------------------------------- Funkprotokoll -> Discord

def _clean(text):
    text = re.sub(r'[\x00-\x1f\x7f]+', ' ', str(text)).strip()
    text = re.sub(r'([\\*_~`|>])', r'\\\1', text)
    return text.replace('@', '@​').replace('<', '<​')


def format_line(room_code, entry):
    who = entry.get('author', '')
    if entry.get('call'):
        who += ' · ' + entry['call']
    icon = '📻' if entry.get('kind') == 'funk' else 'ℹ️'
    prefix = '' if ROOM else f'[{room_code}] '
    return f"{icon} `{entry.get('time', '')}` {prefix}**{_clean(who)}:** {_clean(entry.get('message', ''))}"


def post_radio(room_code, entry):
    """Wird vom Spiel bei jedem Funkeintrag aufgerufen. Nur Warteschlange, blockiert nie."""
    if not WEBHOOK_OK or not room_code or (ROOM and room_code != ROOM):
        return
    _queue.append(format_line(room_code, entry))
    _wake.set()


def _send(content):
    body = {'content': content[:1990], 'username': 'Westbummeln Funk',
            'allowed_mentions': {'parse': []}, 'flags': 4}
    for _ in range(4):
        try:
            status, data = _http('POST', WEBHOOK_URL, body=body)
        except OSError as error:
            _log_once('webhook-net', f'Webhook nicht erreichbar: {error}')
            time.sleep(5)
            continue
        if status in (200, 204):
            return True
        if status == 429:
            time.sleep(min(float(data.get('retry_after', 2) or 2), 30))
            continue
        if status >= 500:
            time.sleep(3)
            continue
        _log_once('webhook', f'Webhook abgelehnt (Status {status}). Webhook-Adresse prüfen oder neu erstellen.')
        return False
    return False


def _sender():
    while True:
        _wake.wait()
        time.sleep(BATCH_SECONDS)       # kurz sammeln, damit mehrere Meldungen eine Nachricht ergeben
        _wake.clear()
        while _queue:
            lines, size = [], 0
            while _queue and size + len(_queue[0]) + 1 <= 1900:
                line = _queue.popleft()
                lines.append(line)
                size += len(line) + 1
            if not lines:                # einzelne überlange Zeile
                lines.append(_queue.popleft()[:1900])
            _send('\n'.join(lines))


# --------------------------------------------------------- Discord -> Funk

def _bot(path):
    return _http('GET', API + path, headers={'Authorization': 'Bot ' + BOT_TOKEN})


def _deliver(message, on_message):
    author = message.get('author') or {}
    if author.get('bot') or message.get('webhook_id') or message.get('type', 0) not in (0, 19):
        return
    text = re.sub(r'<@[!&]?\d+>', '@Nutzer', str(message.get('content') or ''))
    text = re.sub(r'<#\d+>', '#kanal', text)
    text = re.sub(r'\s+', ' ', text).strip()
    if not text:
        if not message.get('attachments') and not message.get('embeds'):
            _log_once('content', 'Nachrichten kommen ohne Text an. Im Developer Portal beim Bot den '
                                 '„Message Content Intent“ einschalten.')
        return
    name = str(author.get('global_name') or author.get('username') or 'Discord')
    on_message(name[:24], text[:400])


def _poller(on_message):
    last = None
    while True:
        wait = POLL_SECONDS
        try:
            if last is None:
                status, data = _bot(f'/channels/{CHANNEL_ID}/messages?limit=1')
                if status == 200 and isinstance(data, list):
                    last = data[0]['id'] if data else '0'     # alte Nachrichten werden nicht nachgespielt
                    print('Discord: Funk-Kanal verbunden.', flush=True)
                else:
                    wait = _poll_problem(status, data)
            else:
                status, data = _bot(f'/channels/{CHANNEL_ID}/messages?limit=50&after={last}')
                if status == 200 and isinstance(data, list):
                    for message in sorted(data, key=lambda m: int(m['id'])):
                        last = message['id']
                        _deliver(message, on_message)
                else:
                    wait = _poll_problem(status, data)
        except Exception as error:
            _log_once('poll', f'Kanal lesen fehlgeschlagen: {error}', 60)
            wait = 10
        time.sleep(wait)


def _poll_problem(status, data):
    if status == 429:
        return min(float(data.get('retry_after', 5) or 5), 60)
    if status in (401, 403, 404):
        hint = {
            401: 'Bot-Token ungültig.',
            403: 'Der Bot darf den Kanal nicht lesen (Rechte „Kanal ansehen“ und „Nachrichtenverlauf lesen“ geben).',
            404: 'Kanal nicht gefunden (Kanal-ID prüfen, Bot zum Server einladen).',
        }[status]
        _log_once('poll-status', f'Kanal lesen: Status {status}. {hint}', 120)
        return 60
    _log_once('poll-status', f'Kanal lesen: unerwarteter Status {status}.', 120)
    return 15


# ----------------------------------------------------------------- Start

def start(on_message):
    if login_enabled():
        print('Discord: Anmeldung aktiv' + (' (nur Mitglieder des Servers).' if GUILD_ID else '.'), flush=True)
    if WEBHOOK_URL and not WEBHOOK_OK:
        print('Discord: DISCORD_WEBHOOK_URL sieht falsch aus '
              '(muss mit https://discord.com/api/webhooks/ beginnen).', flush=True)
    if WEBHOOK_OK:
        print('Discord: Funkprotokoll wird gespiegelt' + (f' (Raum {ROOM}).' if ROOM else ' (alle Räume).'), flush=True)
        threading.Thread(target=_sender, daemon=True).start()
    if BOT_TOKEN and not BOT_OK:
        print('Discord: Bot nicht gestartet. DISCORD_CHANNEL_ID (Zahl) und DISCORD_ROOM (Raumcode) '
              'werden gebraucht.', flush=True)
    if BOT_OK:
        threading.Thread(target=_poller, args=(on_message,), daemon=True).start()
    if VOICE_URL and not VOICE_OK:
        print('Discord: DISCORD_VOICE_URL muss mit https://discord.gg/ beginnen.', flush=True)
