"""Django-Einstellungen für Westbummeln. Alles Veränderliche kommt aus Umgebungsvariablen.

Lokal (ohne Variablen) läuft das Spiel mit SQLite und DEBUG an. Auf Render (Variable RENDER ist
gesetzt) sind DATABASE_URL und SECRET_KEY Pflicht, sonst startet der Dienst nicht. So kann das Spiel
nie unbemerkt auf eine flüchtige SQLite-Datei ausweichen und dabei Konten verlieren.
"""
import os
from pathlib import Path

import dj_database_url
from csp.constants import NONE, SELF, UNSAFE_INLINE
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent
ON_RENDER = bool(os.environ.get('RENDER'))


def env_list(name):
    return [item.strip() for item in os.environ.get(name, '').split(',') if item.strip()]


DEBUG = os.environ.get('DEBUG', '0' if ON_RENDER else '1') == '1'

SECRET_KEY = os.environ.get('SECRET_KEY', '')
if not SECRET_KEY:
    if ON_RENDER:
        raise ImproperlyConfigured('SECRET_KEY fehlt. In Render unter Environment setzen.')
    SECRET_KEY = 'nur-lokal-unsicherer-schluessel'

ALLOWED_HOSTS = env_list('ALLOWED_HOSTS')
CSRF_TRUSTED_ORIGINS = env_list('CSRF_TRUSTED_ORIGINS')
RENDER_HOST = os.environ.get('RENDER_EXTERNAL_HOSTNAME', '').strip()
if RENDER_HOST:
    ALLOWED_HOSTS.append(RENDER_HOST)
    CSRF_TRUSTED_ORIGINS.append(f'https://{RENDER_HOST}')
if DEBUG or not ALLOWED_HOSTS:
    ALLOWED_HOSTS += ['localhost', '127.0.0.1', '[::1]']

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'accounts',
    'game',
]

MIDDLEWARE = [
    'westbummeln.middleware.health_check',
    'django.middleware.security.SecurityMiddleware',
    'csp.middleware.CSPMiddleware',
    'westbummeln.security.security_headers',
    'westbummeln.security.request_guard',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'westbummeln.urls'
WSGI_APPLICATION = 'westbummeln.wsgi.application'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

# ------------------------------------------------------------------ Datenbank
# Render liefert postgres://… bzw. postgresql://…; dj-database-url wählt daraus das
# Postgres-Backend (psycopg 3). Jeder der 8 gunicorn-Threads hält höchstens eine Verbindung,
# die 60 Sekunden wiederverwendet und vor der Wiederverwendung geprüft wird.
DATABASE_URL = os.environ.get('DATABASE_URL', '').strip()
if not DATABASE_URL and ON_RENDER:
    raise ImproperlyConfigured(
        'DATABASE_URL fehlt. Die Postgres-Datenbank westbummeln-db mit dem Webdienst verbinden '
        '(siehe KONTEN.md). Ohne Datenbank würden alle Konten beim Neustart verloren gehen.'
    )
DATABASES = {
    'default': dj_database_url.parse(DATABASE_URL, conn_max_age=60, conn_health_checks=True)
    if DATABASE_URL
    else {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': os.environ.get('SQLITE_PATH', str(BASE_DIR / 'db.sqlite3')),
    }
}
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# --------------------------------------------------------------- Anmeldung
AUTH_USER_MODEL = 'accounts.User'
AUTHENTICATION_BACKENDS = ['accounts.backends.UsernameOrEmailBackend']
# Neue Passwörter: scrypt (wie bisher, speicherhart und auf dem kleinen Render-Server schneller als
# PBKDF2). Alte Hashes (wb_scrypt) werden beim nächsten Login automatisch neu berechnet.
PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.ScryptPasswordHasher',
    'django.contrib.auth.hashers.PBKDF2PasswordHasher',
    'django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher',
    'django.contrib.auth.hashers.Argon2PasswordHasher',
    'django.contrib.auth.hashers.BCryptSHA256PasswordHasher',
    'accounts.hashers.LegacyScryptHasher',
]
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', 'OPTIONS': {'min_length': 8}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

SESSION_COOKIE_AGE = 7 * 86400
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_SAMESITE = 'Lax'
CSRF_FAILURE_VIEW = 'westbummeln.views.csrf_failure'
SECURE_COOKIES = ON_RENDER or os.environ.get('SECURE_COOKIES') == '1'
SESSION_COOKIE_SECURE = SECURE_COOKIES
CSRF_COOKIE_SECURE = SECURE_COOKIES
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_CONTENT_TYPE_NOSNIFF = True

# ------------------------------------------------------------- Sicherheit
# Zähler für IP-Limits und Login-Sperren liegen im Arbeitsspeicher. Das passt, weil gunicorn genau
# einen Worker startet; bei mehreren Workern bräuchte es einen geteilten Cache.
CACHES = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache', 'LOCATION': 'westbummeln'}}

# Wie viele Proxys vor Django stehen und X-Forwarded-For setzen (Produktion: 1, Caddy bzw. Render).
# 0 = REMOTE_ADDR nehmen (lokal ohne Proxy).
TRUSTED_PROXY_COUNT = int(os.environ.get('TRUSTED_PROXY_COUNT', '1' if SECURE_COOKIES else '0'))

# Anfragen je Client-IP. /api ist großzügig: Jeder Spieler fragt alle 1,5 s den Spielstand und
# alle 1,7 s den Sprachfunk ab (ca. 75 Anfragen pro Minute), mehrere Spieler können eine IP teilen.
RATE_LIMITS = {
    'login': os.environ.get('RATE_LIMIT_LOGIN', '10/m'),
    'register': os.environ.get('RATE_LIMIT_REGISTER', '5/h'),
    'discord': os.environ.get('RATE_LIMIT_DISCORD', '10/m'),
    'api': os.environ.get('RATE_LIMIT_API', '240/m'),
}

# Größter Anfragekörper. Spielaktionen und Funksignale sind höchstens 12 000 Bytes groß.
DATA_UPLOAD_MAX_MEMORY_SIZE = 16 * 1024

# HSTS setzt in Produktion der Reverse-Proxy (Caddy). Django nur, wenn ausdrücklich gewünscht
# (z. B. ohne Caddy) – und auch dann nur über HTTPS.
SECURE_HSTS_SECONDS = int(os.environ.get('SECURE_HSTS_SECONDS', '0'))
SECURE_REFERRER_POLICY = 'strict-origin-when-cross-origin'  # Google-Login braucht den Origin im Referer
# Djangos Standard same-origin würde das Popup der Google-Anmeldung von der Seite abtrennen.
SECURE_CROSS_ORIGIN_OPENER_POLICY = 'same-origin-allow-popups'
X_FRAME_OPTIONS = 'DENY'
PERMISSIONS_POLICY = 'microphone=(self), camera=(), geolocation=(), payment=(), usb=()'

# Content-Security-Policy (django-csp). Google-Pfade wie von Google für „Sign in with Google“ angegeben.
# 'unsafe-inline' gilt nur für Styles, nie für Skripte: Das Spiel positioniert Kartenpunkte und
# Fortschrittsbalken mit style="left:…%", und Googles Anmeldeskript hängt beim Zeichnen des Buttons einen
# eigenen <style>-Block an (ohne ihn zerfällt der Button). Dessen Inhalt ändert sich mit Googles Updates,
# ein fester Hash würde den Button irgendwann still kaputtmachen. Über CSS lässt sich kein Code ausführen.
GOOGLE_GSI = 'https://accounts.google.com/gsi/'
CONTENT_SECURITY_POLICY = {
    'DIRECTIVES': {
        'default-src': [SELF],
        'script-src': [SELF, GOOGLE_GSI + 'client'],
        'style-src': [SELF, UNSAFE_INLINE, GOOGLE_GSI + 'style'],
        'img-src': [SELF, 'data:'],
        'connect-src': [SELF, GOOGLE_GSI],
        'frame-src': [GOOGLE_GSI],
        'object-src': [NONE],
        'base-uri': [NONE],
        'form-action': [SELF],
        'frame-ancestors': [NONE],
    },
}

# ----------------------------------------------------------- Sprache, Zeit
LANGUAGE_CODE = 'de'
# UTC wie bisher auf Render: Die Uhrzeiten im Funkprotokoll stammen aus time.strftime.
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# ------------------------------------------------------- Statische Dateien
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']
STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {
        'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'
        if DEBUG
        else 'whitenoise.storage.CompressedManifestStaticFilesStorage',
    },
}

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {'console': {'class': 'logging.StreamHandler'}},
    'root': {'handlers': ['console'], 'level': 'WARNING'},
}
