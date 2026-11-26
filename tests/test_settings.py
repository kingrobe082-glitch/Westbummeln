"""Einstellungen: Auf Render darf der Dienst nie ohne Postgres oder SECRET_KEY starten."""
import os
import subprocess
import sys
from pathlib import Path

import dj_database_url

ROOT = Path(__file__).resolve().parent.parent


def start_django(**env):
    clean = {k: v for k, v in os.environ.items() if k not in ('DATABASE_URL', 'SECRET_KEY', 'RENDER')}
    return subprocess.run(
        [sys.executable, '-c', 'import django; django.setup(); from django.conf import settings; '
                               'print(settings.DATABASES["default"]["ENGINE"])'],
        cwd=ROOT, env={**clean, 'DJANGO_SETTINGS_MODULE': 'westbummeln.settings', 'PYTHONIOENCODING': 'utf-8', **env},
        capture_output=True, text=True, encoding='utf-8')


def test_render_without_database_url_refuses_to_start():
    result = start_django(RENDER='true', SECRET_KEY='x')
    assert result.returncode != 0
    assert 'DATABASE_URL fehlt' in result.stderr


def test_render_without_secret_key_refuses_to_start():
    result = start_django(RENDER='true', DATABASE_URL='postgres://u:p@db:5432/wb')
    assert result.returncode != 0
    assert 'SECRET_KEY fehlt' in result.stderr


def test_local_default_is_sqlite():
    result = start_django()
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == 'django.db.backends.sqlite3'


def test_render_style_urls_use_postgres():
    for url in ('postgres://u:p@dpg-abc/westbummeln', 'postgresql://u:p@dpg-abc/westbummeln'):
        config = dj_database_url.parse(url, conn_max_age=60, conn_health_checks=True)
        assert config['ENGINE'] == 'django.db.backends.postgresql'
        assert config['CONN_HEALTH_CHECKS'] is True
