"""Sichert die Konten automatisch in ein privates GitHub-Repo und stellt sie beim Start wieder her.
Nur Standardbibliothek. Aktiv, wenn BACKUP_GITHUB_TOKEN und BACKUP_GITHUB_REPO gesetzt sind.

Sicherheitsregeln: Es wird nie gesichert, bevor der Start-Check (Zugriff + Wiederherstellung) geklappt hat,
und eine leere Datenbank überschreibt nie eine vorhandene Sicherung."""
import base64
import hashlib
import json
import os
import signal
import threading
import time
import urllib.error
import urllib.request

import accounts

TOKEN = os.environ.get('BACKUP_GITHUB_TOKEN', '').strip()
REPO = os.environ.get('BACKUP_GITHUB_REPO', '').strip()          # z. B. meinname/westbummeln-konten
FILE = os.environ.get('BACKUP_FILE', 'accounts-backup.json').strip()
BRANCH = os.environ.get('BACKUP_GITHUB_BRANCH', 'main').strip()
ENABLED = bool(TOKEN and REPO)

HINTS = {
    401: 'Token ungültig oder abgelaufen.',
    403: 'Token darf nicht schreiben (nötig: Contents = Read and write).',
    404: 'Repo nicht gefunden oder Token hat keinen Zugriff darauf (Repo-Name und Token prüfen).',
    409: 'Konflikt, wird erneut versucht.',
    422: 'Branch oder Datei passt nicht (Branch-Name prüfen), wird erneut versucht.',
}

_event = threading.Event()
_push_lock = threading.Lock()
_last_hash = None
_ready = False          # erst nach erfolgreichem Start-Check darf gesichert werden
_notified = False


class AccessDenied(RuntimeError):
    """Token oder Repo-Name falsch: Wiederholen hilft nicht."""


def _problem(status):
    return f'Status {status}: ' + HINTS.get(status, 'unerwartete Antwort von GitHub.')


def _request(method, body=None, repo_only=False):
    url = f'https://api.github.com/repos/{REPO}'
    if not repo_only:
        url += f'/contents/{FILE}' + (f'?ref={BRANCH}' if method == 'GET' else '')
    req = urllib.request.Request(url, method=method, data=json.dumps(body).encode() if body else None, headers={
        'Authorization': f'Bearer {TOKEN}', 'Accept': 'application/vnd.github+json',
        'User-Agent': 'westbummeln-backup', 'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, json.loads(r.read() or b'{}')
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b'{}')
        except ValueError:
            return e.code, {}


def _b64(value):
    return base64.b64encode(value).decode() if value is not None else None


def _unb64(value):
    return base64.b64decode(value) if value is not None else None


def _account_count():
    with accounts.database() as db:
        return db.execute('SELECT COUNT(*) FROM accounts').fetchone()[0]


def export_text():
    with accounts.database() as db:
        rows = db.execute('SELECT id,name,name_key,salt,password,google_sub,email,discord_sub FROM accounts ORDER BY id').fetchall()
        devs = [r[0] for r in db.execute('SELECT account FROM developers ORDER BY account')]
    data = {'version': 1, 'developers': devs, 'accounts': [
        {'id': r[0], 'name': r[1], 'name_key': r[2], 'salt': _b64(r[3]), 'password': _b64(r[4]),
         'google_sub': r[5], 'email': r[6], 'discord_sub': r[7]} for r in rows]}
    return json.dumps(data, sort_keys=True, indent=1)


def import_text(text):
    data = json.loads(text)
    with accounts.database() as db:
        for a in data['accounts']:
            db.execute('INSERT OR IGNORE INTO accounts (id,name,name_key,salt,password,google_sub,email,discord_sub) VALUES (?,?,?,?,?,?,?,?)',
                       (a['id'], a['name'], a['name_key'], _unb64(a['salt']), _unb64(a['password']),
                        a.get('google_sub'), a.get('email'), a.get('discord_sub')))
        for account in data.get('developers', []):
            db.execute('INSERT OR IGNORE INTO developers VALUES (?)', (account,))
    return len(data['accounts'])


def check_access():
    status, _ = _request('GET', repo_only=True)
    if status in (401, 403, 404):
        raise AccessDenied(_problem(status))
    if status != 200:
        raise RuntimeError(_problem(status))


def restore():
    """Ist die lokale Datenbank leer, werden die Konten aus dem Backup geholt."""
    global _last_hash
    if _account_count():
        return
    status, data = _request('GET')
    if status == 404:
        print('Backup: Repo erreichbar, noch keine Sicherung vorhanden.', flush=True)
        return
    if status != 200:
        raise RuntimeError(_problem(status))
    count = import_text(base64.b64decode(data['content']).decode())
    _last_hash = hashlib.sha256(export_text().encode()).hexdigest()
    print(f'Backup: {count} Konten wiederhergestellt.', flush=True)


def _prepare():
    global _ready
    check_access()
    restore()
    _ready = True


def push():
    global _last_hash
    if not _account_count():
        return                       # eine leere Datenbank überschreibt nie eine Sicherung
    text = export_text()
    digest = hashlib.sha256(text.encode()).hexdigest()
    if digest == _last_hash:
        return
    status, data = _request('GET')
    if status not in (200, 404):
        raise RuntimeError(_problem(status))
    body = {'message': 'Konten-Backup', 'branch': BRANCH, 'content': base64.b64encode(text.encode()).decode()}
    if status == 200:
        body['sha'] = data['sha']
    status, _ = _request('PUT', body)
    if status not in (200, 201):
        raise RuntimeError(_problem(status))
    _last_hash = digest
    print(f'Backup: {len(json.loads(text)["accounts"])} Konten gesichert.', flush=True)


def flush():
    if ENABLED and _ready:
        with _push_lock:
            push()


def mark_dirty():
    if ENABLED:
        _event.set()


def _retry_prepare():
    global _notified
    if _account_count():
        if not _notified:
            print('Backup: pausiert bis zum nächsten Neustart (es gibt neue Konten, '
                  'aber die alte Sicherung konnte nicht geladen werden).', flush=True)
            _notified = True
        return
    try:
        _prepare()
        print('Backup: wieder verbunden.', flush=True)
    except Exception as error:
        print('Backup: GitHub weiterhin nicht erreichbar:', error, flush=True)


def _worker():
    while True:
        _event.wait(None if _ready else 30)
        if not _ready:
            _retry_prepare()
            if not _ready:
                continue
        time.sleep(3)          # kurz sammeln, damit mehrere Änderungen eine Sicherung ergeben
        _event.clear()
        try:
            flush()
        except Exception as error:
            print('Backup fehlgeschlagen:', error, flush=True)
            time.sleep(30)
            _event.set()


def _on_sigterm(*_):
    try:
        flush()
    except Exception as error:
        print('Backup beim Beenden fehlgeschlagen:', error, flush=True)
    finally:
        raise SystemExit(0)


def start():
    if not ENABLED:
        print('Backup: aus (BACKUP_GITHUB_TOKEN/BACKUP_GITHUB_REPO nicht gesetzt).', flush=True)
        return
    for attempt in range(3):
        try:
            _prepare()
            print('Backup: bereit.', flush=True)
            break
        except AccessDenied as error:
            print('Backup: KEIN ZUGRIFF auf GitHub.', error, 'Sicherungen sind aus.', flush=True)
            return
        except Exception as error:
            print(f'Backup: Start-Check fehlgeschlagen ({error}), Versuch {attempt + 1} von 3.', flush=True)
            time.sleep(3)
    else:
        print('Backup: GitHub nicht erreichbar. Sicherungen pausieren, bis es klappt.', flush=True)
    threading.Thread(target=_worker, daemon=True).start()
    signal.signal(signal.SIGTERM, _on_sigterm)
