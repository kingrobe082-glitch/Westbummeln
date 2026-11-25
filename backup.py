"""Sichert die Konten automatisch in ein privates GitHub-Repo und stellt sie beim Start wieder her.
Nur Standardbibliothek. Aktiv, wenn BACKUP_GITHUB_TOKEN und BACKUP_GITHUB_REPO gesetzt sind."""
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
REPO = os.environ.get('BACKUP_GITHUB_REPO', '').strip()          # z. B. meinname/westbummeln-backup
FILE = os.environ.get('BACKUP_FILE', 'accounts-backup.json').strip()
BRANCH = os.environ.get('BACKUP_GITHUB_BRANCH', 'main').strip()
ENABLED = bool(TOKEN and REPO)

_event = threading.Event()
_push_lock = threading.Lock()
_last_hash = None


def _request(method, body=None):
    url = f'https://api.github.com/repos/{REPO}/contents/{FILE}'
    if method == 'GET':
        url += f'?ref={BRANCH}'
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


def export_text():
    with accounts.database() as db:
        rows = db.execute('SELECT id,name,name_key,salt,password,google_sub,email FROM accounts ORDER BY id').fetchall()
        devs = [r[0] for r in db.execute('SELECT account FROM developers ORDER BY account')]
    data = {'version': 1, 'developers': devs, 'accounts': [
        {'id': r[0], 'name': r[1], 'name_key': r[2], 'salt': _b64(r[3]), 'password': _b64(r[4]),
         'google_sub': r[5], 'email': r[6]} for r in rows]}
    return json.dumps(data, sort_keys=True, indent=1)


def import_text(text):
    data = json.loads(text)
    with accounts.database() as db:
        for a in data['accounts']:
            db.execute('INSERT OR IGNORE INTO accounts (id,name,name_key,salt,password,google_sub,email) VALUES (?,?,?,?,?,?,?)',
                       (a['id'], a['name'], a['name_key'], _unb64(a['salt']), _unb64(a['password']),
                        a['google_sub'], a['email']))
        for account in data.get('developers', []):
            db.execute('INSERT OR IGNORE INTO developers VALUES (?)', (account,))
    return len(data['accounts'])


def restore():
    """Beim Start: Ist die lokale Datenbank leer, werden die Konten aus dem Backup geholt."""
    global _last_hash
    if not ENABLED:
        return
    with accounts.database() as db:
        if db.execute('SELECT COUNT(*) FROM accounts').fetchone()[0]:
            return
    status, data = _request('GET')
    if status == 404:
        print('Backup: noch keine Sicherung vorhanden.', flush=True)
        return
    if status != 200:
        raise RuntimeError(f'GitHub antwortet mit Status {status}')
    count = import_text(base64.b64decode(data['content']).decode())
    _last_hash = hashlib.sha256(export_text().encode()).hexdigest()
    print(f'Backup: {count} Konten wiederhergestellt.', flush=True)


def push():
    global _last_hash
    text = export_text()
    digest = hashlib.sha256(text.encode()).hexdigest()
    if digest == _last_hash:
        return
    status, data = _request('GET')
    if status not in (200, 404):
        raise RuntimeError(f'GitHub antwortet mit Status {status}')
    body = {'message': 'Konten-Backup', 'branch': BRANCH, 'content': base64.b64encode(text.encode()).decode()}
    if status == 200:
        body['sha'] = data['sha']
    status, _ = _request('PUT', body)
    if status not in (200, 201):
        raise RuntimeError(f'Sicherung fehlgeschlagen (Status {status})')
    _last_hash = digest


def flush():
    if ENABLED:
        with _push_lock:
            push()


def mark_dirty():
    if ENABLED:
        _event.set()


def _worker():
    while True:
        _event.wait()
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
    finally:
        raise SystemExit(0)


def start():
    if not ENABLED:
        print('Backup: aus (BACKUP_GITHUB_TOKEN/BACKUP_GITHUB_REPO nicht gesetzt).', flush=True)
        return
    try:
        restore()
    except Exception as error:
        print('Backup: Wiederherstellung fehlgeschlagen:', error, flush=True)
    threading.Thread(target=_worker, daemon=True).start()
    signal.signal(signal.SIGTERM, _on_sigterm)
