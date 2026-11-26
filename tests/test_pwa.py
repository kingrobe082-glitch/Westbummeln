"""Progressive Web App: Manifest, Service Worker, Offline-Seite, Icons und Einbindung im <head>."""
import json

import pytest
from django.contrib.staticfiles import finders
from django.templatetags.static import static

from westbummeln import pwa

pytestmark = pytest.mark.django_db


def sw_config(response):
    first_line = response.content.decode().split('\n', 1)[0]
    assert first_line.startswith('const CONFIG = ') and first_line.endswith(';')
    return json.loads(first_line.removeprefix('const CONFIG = ').removesuffix(';'))


def test_manifest(client):
    response = client.get('/manifest.webmanifest')
    assert response.status_code == 200
    assert response['Content-Type'] == 'application/manifest+json'
    assert response['Cache-Control'] == 'no-cache'
    data = json.loads(response.content)
    assert data['name'] == 'Westbummeln – Leitstelle'
    assert data['short_name'] == 'Westbummeln'
    assert (data['start_url'], data['scope'], data['display'], data['lang']) == ('/', '/', 'standalone', 'de')
    assert (data['theme_color'], data['background_color']) == ('#15263a', '#0a111b')
    icons = {(icon['sizes'], icon['purpose']): icon['src'] for icon in data['icons']}
    assert {('192x192', 'any'), ('512x512', 'any'), ('512x512', 'maskable')} <= icons.keys()
    for src in icons.values():
        assert finders.find(src.removeprefix('/static/')), src


def test_service_worker_headers_and_config(client):
    response = client.get('/sw.js')
    assert response.status_code == 200
    assert response['Content-Type'].startswith('text/javascript')
    assert response['Cache-Control'] == 'no-cache'
    assert response['Service-Worker-Allowed'] == '/'
    config = sw_config(response)
    assert len(config['version']) == 12
    assert config['offline'] == '/offline' and '/offline' in config['shell']
    assert static('css/app.css') in config['shell'] and static('karte.webp') in config['shell']
    # Spielstand, Konto, Admin und Anmeldung dürfen nie in den Cache.
    assert {'/api', '/account', '/admin', '/auth', '/healthz'} <= set(config['networkOnly'])
    assert not any(url.startswith(('/api', '/account', '/admin', '/auth')) for url in config['shell'])
    assert 'skipWaiting' in response.content.decode()
    assert "request.method !== 'GET'" in response.content.decode()  # POSTs fasst der Worker nicht an


def test_service_worker_version_follows_file_contents(client, settings, monkeypatch, tmp_path):
    settings.DEBUG = True  # lokal wird die Version bei jedem Abruf neu berechnet
    before = sw_config(client.get('/sw.js'))['version']
    changed = tmp_path / 'app.css'
    changed.write_text('body{color:red}')
    original_find = finders.find
    monkeypatch.setattr(pwa.finders, 'find', lambda name, **kw: str(changed) if name == 'css/app.css'
                        else original_find(name, **kw))
    assert sw_config(client.get('/sw.js'))['version'] != before


def test_shell_files_exist():
    for name in pwa.SHELL_FILES:
        assert finders.find(name), name


def test_offline_page(client):
    response = client.get('/offline')
    assert response.status_code == 200
    assert response['Content-Type'].startswith('text/html')
    assert 'Keine Verbindung' in response.content.decode()
    assert 'Das Spiel braucht Internet' in response.content.decode()


@pytest.mark.parametrize('path', ['/favicon.ico', '/apple-touch-icon.png'])
def test_root_icons(client, path):
    response = client.get(path)
    assert response.status_code == 200
    assert response['Content-Type'].startswith('image/')
    assert b''.join(response.streaming_content)


def test_pwa_routes_reject_post(client):
    for path in ('/manifest.webmanifest', '/sw.js', '/offline', '/favicon.ico'):
        assert client.post(path).status_code in (404, 405), path


def test_head_links_pwa(client):
    html = client.get('/').content.decode()
    head = html.split('</head>', 1)[0]
    for snippet in ('<link rel="manifest" href="/manifest.webmanifest">', '<meta name="theme-color" content="#15263a">',
                    static('icons/apple-touch-icon.png'), 'apple-mobile-web-app-capable',
                    static('js/pwa.js'), static('css/pwa.css')):
        assert snippet in head, snippet
    assert '<script>' not in html  # CSP: keine Inline-Skripte
