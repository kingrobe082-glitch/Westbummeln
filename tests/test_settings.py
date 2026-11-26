"""Einstellungen: In Produktion darf der Dienst nie ohne Postgres, SECRET_KEY oder ALLOWED_HOSTS starten."""
import os
import subprocess
import sys
from pathlib import Path

import dj_database_url

ROOT = Path(__file__).resolve().parent.parent
PROD_ENV = {
    'DJANGO_ENV': 'prod',
    'SECRET_KEY': 'x' * 50,
    'DATABASE_URL': 'postgresql://u:p@db:5432/wb',
    'ALLOWED_HOSTS': 'westbummeln.example',
}
CLEARED = ('DATABASE_URL', 'SECRET_KEY', 'RENDER', 'RENDER_EXTERNAL_HOSTNAME', 'DJANGO_ENV', 'DEBUG',
           'ALLOWED_HOSTS', 'CSRF_TRUSTED_ORIGINS', 'SECURE_COOKIES')
PRINT = ('import django; django.setup(); from django.conf import settings as s; '
         'print(s.DATABASES["default"]["ENGINE"], s.DEBUG, s.SESSION_COOKIE_SECURE, s.CSRF_COOKIE_SECURE, '
         'sorted(s.ALLOWED_HOSTS))')


def start_django(**env):
    clean = {k: v for k, v in os.environ.items() if k not in CLEARED}
    return subprocess.run(
        [sys.executable, '-c', PRINT],
        cwd=ROOT, env={**clean, 'DJANGO_SETTINGS_MODULE': 'westbummeln.settings', 'PYTHONIOENCODING': 'utf-8', **env},
        capture_output=True, text=True, encoding='utf-8')


def prod(**overrides):
    env = {**PROD_ENV, **overrides}
    return start_django(**{k: v for k, v in env.items() if v is not None})


def test_production_without_database_url_refuses_to_start():
    result = prod(DATABASE_URL=None)
    assert result.returncode != 0
    assert 'DATABASE_URL fehlt' in result.stderr


def test_production_without_secret_key_refuses_to_start():
    result = prod(SECRET_KEY=None)
    assert result.returncode != 0
    assert 'SECRET_KEY fehlt' in result.stderr


def test_production_without_allowed_hosts_refuses_to_start():
    result = prod(ALLOWED_HOSTS=None)
    assert result.returncode != 0
    assert 'ALLOWED_HOSTS fehlt' in result.stderr


def test_production_refuses_debug():
    result = prod(DEBUG='1')
    assert result.returncode != 0
    assert 'DEBUG=1' in result.stderr


def test_unknown_django_env_refuses_to_start():
    result = start_django(DJANGO_ENV='production')
    assert result.returncode != 0
    assert 'DJANGO_ENV' in result.stderr


def test_production_uses_postgres_secure_cookies_and_only_given_hosts():
    result = prod()
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().split(maxsplit=4) == [
        'django.db.backends.postgresql', 'False', 'True', 'True', "['westbummeln.example']"]


def test_render_variable_still_means_production():
    result = start_django(RENDER='true', SECRET_KEY='x', RENDER_EXTERNAL_HOSTNAME='westbummeln.onrender.com')
    assert result.returncode != 0
    assert 'DATABASE_URL fehlt' in result.stderr
    result = start_django(RENDER='true', SECRET_KEY='x' * 50, DATABASE_URL='postgres://u:p@dpg-abc/wb',
                          RENDER_EXTERNAL_HOSTNAME='westbummeln-multiplayer.onrender.com')
    assert result.returncode == 0, result.stderr
    assert "['westbummeln-multiplayer.onrender.com']" in result.stdout


def test_local_default_is_sqlite_with_debug():
    result = start_django()
    assert result.returncode == 0, result.stderr
    engine, debug, session_secure, csrf_secure, _hosts = result.stdout.split(maxsplit=4)
    assert (engine, debug, session_secure, csrf_secure) == ('django.db.backends.sqlite3', 'True', 'False', 'False')


def test_postgres_urls_use_postgres_backend():
    for url in ('postgres://u:p@db/westbummeln', 'postgresql://u:p@db:5432/westbummeln'):
        config = dj_database_url.parse(url, conn_max_age=60, conn_health_checks=True)
        assert config['ENGINE'] == 'django.db.backends.postgresql'
        assert config['CONN_HEALTH_CHECKS'] is True
