from contextlib import contextmanager
from hashlib import scrypt, sha256
from hmac import compare_digest
from http.cookies import SimpleCookie, CookieError
from pathlib import Path
import os
import re
import secrets
import sqlite3
import time

COOKIE = 'wb_account'
LIFETIME = 7 * 86400
GOOGLE_CLIENT_ID = os.environ.get('GOOGLE_CLIENT_ID', '').strip()
DB_PATH = Path(os.environ.get('ACCOUNT_DB_PATH', str(Path(__file__).with_name('accounts.sqlite3'))))


@contextmanager
def database():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH)
    try:
        with db:
            db.execute('''CREATE TABLE IF NOT EXISTS accounts (
                id INTEGER PRIMARY KEY, name TEXT NOT NULL,
                name_key TEXT UNIQUE, salt BLOB, password BLOB, google_sub TEXT UNIQUE
            )''')
            db.execute('''CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY, account INTEGER NOT NULL REFERENCES accounts(id),
                expires INTEGER NOT NULL
            )''')
            db.execute('''CREATE TABLE IF NOT EXISTS developers (
                account INTEGER PRIMARY KEY REFERENCES accounts(id)
            )''')
            yield db
    finally:
        db.close()


def password_hash(password, salt):
    return scrypt(password.encode(), salt=salt, n=2**15, r=8, p=1, maxmem=64 * 1024**2)


def account_for_password(db, data, register):
    name = str(data.get('name', '')).strip()
    password = data.get('password')
    if not isinstance(password, str) or not 1 <= len(password) <= 128:
        raise ValueError('Bitte gib ein Passwort mit höchstens 128 Zeichen ein.')
    if register:
        if not re.fullmatch(r'[\w-]{3,24}', name):
            raise ValueError('Benutzername: 3–24 Buchstaben, Zahlen, Unterstriche oder Bindestriche.')
        if len(password) < 8:
            raise ValueError('Das Passwort braucht mindestens 8 Zeichen.')
        salt = secrets.token_bytes(16)
        hashed = password_hash(password, salt)
        try:
            row = db.execute('INSERT INTO accounts (name,name_key,salt,password) VALUES (?,?,?,?)',
                             (name, name.casefold(), salt, hashed))
        except sqlite3.IntegrityError:
            raise ValueError('Dieser Benutzername ist bereits vergeben.') from None
        return row.lastrowid, name
    row = db.execute('SELECT id,name,salt,password FROM accounts WHERE name_key=?',
                     (name.casefold(),)).fetchone()
    hashed = password_hash(password, row[2] if row else bytes(16))
    if not row or not compare_digest(hashed, row[3]):
        raise ValueError('Benutzername oder Passwort stimmt nicht.')
    return row[:2]


def account_for_google(db, data, nonce):
    credential = data.get('credential')
    if not GOOGLE_CLIENT_ID or not nonce or not isinstance(credential, str):
        raise ValueError('Google-Anmeldung ist gerade nicht verfügbar.')
    from google.auth.transport.requests import Request
    from google.oauth2 import id_token

    try:
        claims = id_token.verify_oauth2_token(credential, Request(), GOOGLE_CLIENT_ID)
        subject = claims['sub']
        token_nonce = claims.get('nonce')
        if not isinstance(token_nonce, str) or not compare_digest(token_nonce, nonce):
            raise ValueError('Nonce ungültig')
    except (ValueError, KeyError):
        raise ValueError('Google-Anmeldung fehlgeschlagen. Bitte lade die Seite neu.') from None
    name = 'Funk-' + secrets.token_hex(4)
    db.execute('INSERT INTO accounts (name,google_sub) VALUES (?,?) ON CONFLICT(google_sub) DO NOTHING',
               (name, subject))
    return db.execute('SELECT id,name FROM accounts WHERE google_sub=?', (subject,)).fetchone()


def cookie_value(header, name):
    jar = SimpleCookie()
    try:
        jar.load(header or '')
    except CookieError:
        return ''
    return jar[name].value if name in jar else ''


def make_cookie(name, value, age, secure):
    return f'{name}={value}; Path=/; HttpOnly; SameSite=Lax; Max-Age={age}' + ('; Secure' if secure else '')


def token_key(token):
    return sha256(token.encode()).hexdigest()


def current_account(header):
    token = cookie_value(header, COOKIE)
    if not token:
        return None
    with database() as db:
        row = db.execute('''SELECT accounts.id,name,EXISTS(SELECT 1 FROM developers WHERE developers.account=accounts.id)
                            FROM accounts JOIN sessions ON accounts.id=sessions.account
                            WHERE token=? AND expires>?''', (token_key(token), int(time.time()))).fetchone()
    return row


def authenticate(action, data, header):
    with database() as db:
        old_token = cookie_value(header, COOKIE)
        if action == 'logout':
            db.execute('DELETE FROM sessions WHERE token=?', (token_key(old_token),))
            return None, ''
        if action == 'google':
            account, name = account_for_google(db, data, cookie_value(header, 'wb_google_nonce'))
        else:
            account, name = account_for_password(db, data, action == 'register')
        token = secrets.token_urlsafe(32)
        now = int(time.time())
        db.execute('DELETE FROM sessions WHERE expires<=? OR token=?', (now, token_key(old_token)))
        db.execute('INSERT INTO sessions VALUES (?,?,?)', (token_key(token), account, now + LIFETIME))
        return name, token


def provision_developer():
    name = os.environ.get('DEVELOPER_USERNAME', '').strip()
    password = os.environ.get('DEVELOPER_PASSWORD', '')
    if not name and not password:
        return
    if not re.fullmatch(r'[\w-]{3,24}', name) or not 16 <= len(password) <= 128:
        raise RuntimeError('DEVELOPER_USERNAME und DEVELOPER_PASSWORD prüfen (Passwort: 16–128 Zeichen).')

    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute(
            'SELECT id FROM accounts WHERE name_key=?', (name.casefold(),)
        ).fetchone()
        if not row:
            account, _ = account_for_password(db, {'name': name, 'password': password}, True)
            db.execute('INSERT INTO developers VALUES (?)', (account,))
        elif not db.execute('SELECT 1 FROM developers WHERE account=?', row).fetchone():
            raise RuntimeError('Der Entwicklername gehört bereits einem normalen Konto. Wähle einen anderen Namen.')
