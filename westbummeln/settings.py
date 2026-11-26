"""Django-Einstellungen für Westbummeln. Alles Veränderliche kommt aus Umgebungsvariablen.

Lokal (ohne Variablen) läuft das Spiel mit SQLite und DEBUG an. In Produktion (DJANGO_ENV=prod,
gesetzt im Docker-Compose des Servers) sind DATABASE_URL, SECRET_KEY und ALLOWED_HOSTS Pflicht,
sonst startet der Dienst nicht. So kann das Spiel nie unbemerkt auf eine flüchtige SQLite-Datei
ausweichen und dabei Konten verlieren.
"""
import os
from pathlib import Path

import dj_database_url
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent

# 'prod' auf dem Server (deploy/docker-compose.prod.yml), sonst 'dev'. Eine gesetzte Variable
# RENDER (alter Render-Dienst) gilt weiter als Produktion.
DJANGO_ENV = os.environ.get('DJANGO_ENV', '').strip().lower() or ('prod' if os.environ.get('RENDER') else 'dev')
if DJANGO_ENV not in ('prod', 'dev'):
    raise ImproperlyConfigured(f'DJANGO_ENV muss "prod" oder "dev" sein, nicht "{DJANGO_ENV}".')
PRODUCTION = DJANGO_ENV == 'prod'


def env_list(name):
    return [item.strip() for item in os.environ.get(name, '').split(',') if item.strip()]


DEBUG = os.environ.get('DEBUG', '0' if PRODUCTION else '1') == '1'
if PRODUCTION and DEBUG:
    raise ImproperlyConfigured('DEBUG=1 ist in Produktion (DJANGO_ENV=prod) nicht erlaubt.')

SECRET_KEY = os.environ.get('SECRET_KEY', '')
if not SECRET_KEY:
    if PRODUCTION:
        raise ImproperlyConfigured('SECRET_KEY fehlt. In /opt/westbummeln/.env setzen (deploy/RUNBOOK.md).')
    SECRET_KEY = 'nur-lokal-unsicherer-schluessel'

ALLOWED_HOSTS = env_list('ALLOWED_HOSTS')
CSRF_TRUSTED_ORIGINS = env_list('CSRF_TRUSTED_ORIGINS')
RENDER_HOST = os.environ.get('RENDER_EXTERNAL_HOSTNAME', '').strip()
if RENDER_HOST:
    ALLOWED_HOSTS.append(RENDER_HOST)
    CSRF_TRUSTED_ORIGINS.append(f'https://{RENDER_HOST}')
if PRODUCTION and not ALLOWED_HOSTS:
    raise ImproperlyConfigured('ALLOWED_HOSTS fehlt. In /opt/westbummeln/.env die Domain eintragen.')
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
# DATABASE_URL ist postgres://… bzw. postgresql://…; dj-database-url wählt daraus das
# Postgres-Backend (psycopg 3). Jeder der 8 gunicorn-Threads hält höchstens eine Verbindung,
# die 60 Sekunden wiederverwendet und vor der Wiederverwendung geprüft wird.
DATABASE_URL = os.environ.get('DATABASE_URL', '').strip()
if not DATABASE_URL and PRODUCTION:
    raise ImproperlyConfigured(
        'DATABASE_URL fehlt. In /opt/westbummeln/.env setzen (deploy/RUNBOOK.md). '
        'Ohne Datenbank würden alle Konten beim Neustart verloren gehen.'
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
# Neue Passwörter: scrypt (wie bisher, speicherhart und auf dem kleinen Server schneller als
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
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
]

SESSION_COOKIE_AGE = 7 * 86400
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_SAMESITE = 'Lax'
CSRF_FAILURE_VIEW = 'westbummeln.views.csrf_failure'
SECURE_COOKIES = PRODUCTION or os.environ.get('SECURE_COOKIES') == '1'
SESSION_COOKIE_SECURE = SECURE_COOKIES
CSRF_COOKIE_SECURE = SECURE_COOKIES
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_CONTENT_TYPE_NOSNIFF = True

# ----------------------------------------------------------- Sprache, Zeit
LANGUAGE_CODE = 'de'
# UTC wie bisher: Die Uhrzeiten im Funkprotokoll stammen aus time.strftime.
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
