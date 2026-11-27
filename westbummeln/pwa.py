"""Progressive Web App: Manifest, Service Worker, Offline-Seite und Icons unter festen Root-Adressen.

Der Service Worker muss unter /sw.js liegen (nicht unter /static/), damit er die ganze Seite (Scope /)
steuern darf. Er cacht nur die App-Hülle (CSS, JS, Karte, Icons, Offline-Seite); Spielstand, Konto,
Admin und Anmeldung gehen immer übers Netz. Die Cache-Version ist ein Hash über den Inhalt aller
Hüllen-Dateien: Jede Änderung ergibt eine neue sw.js, der Browser installiert sie und räumt den alten
Cache weg, ohne dass jemand etwas leeren muss.
"""
import functools
import hashlib
import json
from pathlib import Path

from django.conf import settings
from django.contrib.staticfiles import finders
from django.http import FileResponse, HttpResponse, JsonResponse
from django.shortcuts import render
from django.templatetags.static import static
from django.views.decorators.http import require_GET

from westbummeln.views import not_found

SW_SOURCE = Path(__file__).resolve().parent / 'sw.js'
OFFLINE_URL = '/offline'
THEME_COLOR = '#15263a'
BACKGROUND_COLOR = '#0a111b'

# Alles, was die Seite zum Anzeigen braucht (und die Offline-Seite). Pfade relativ zu static/.
SHELL_FILES = [
    'css/app.css', 'css/pwa.css',
    'js/agegate.js', 'js/app.js', 'js/game.js', 'js/voice.js', 'js/account.js', 'js/security.js',
    'js/privacy.js', 'js/pwa.js',
    'js/fme.js', 'js/fms.js', 'css/fme.css', 'sounds/Westbummeln_FME_ZVEI.wav',
    'karte.webp',
    'icons/icon.svg', 'icons/icon-192.png', 'icons/icon-512.png', 'icons/apple-touch-icon.png',
]
# Nie aus dem Cache und nie vom Service Worker angefasst (immer direkt übers Netz).
NETWORK_ONLY = ['/api', '/account', '/admin', '/auth', '/developer', '/healthz', '/sw.js',
                '/manifest.webmanifest']
# Icons, die Browser auch ohne Link-Tag an der Wurzel suchen.
ROOT_FILES = {'favicon.ico': 'icons/favicon.ico', 'apple-touch-icon.png': 'icons/apple-touch-icon.png'}


def _shell_version():
    digest = hashlib.sha256(SW_SOURCE.read_bytes())
    digest.update((settings.BASE_DIR / 'templates' / 'offline.html').read_bytes())
    for name in SHELL_FILES:
        path = finders.find(name)
        if not path:
            raise FileNotFoundError(f'PWA-Hülle: static/{name} fehlt')
        digest.update(name.encode() + b'\0' + Path(path).read_bytes())
    return digest.hexdigest()[:12]


_cached_shell_version = functools.cache(_shell_version)


def shell_version():
    """In Produktion einmal pro Prozess berechnet, lokal (DEBUG) bei jedem Abruf neu."""
    return _shell_version() if settings.DEBUG else _cached_shell_version()


@require_GET
def manifest(request):
    data = {
        'id': '/',
        'name': 'Westbummeln – Leitstelle',
        'short_name': 'Westbummeln',
        'description': 'Multiplayer-Leitstellenspiel der Feuerwehr Westbummeln: Einsätze, Alarmierung, Funk.',
        'lang': 'de',
        'dir': 'ltr',
        'start_url': '/',
        'scope': '/',
        'display': 'standalone',
        'theme_color': THEME_COLOR,
        'background_color': BACKGROUND_COLOR,
        'categories': ['games'],
        'icons': [
            {'src': static('icons/icon-192.png'), 'sizes': '192x192', 'type': 'image/png', 'purpose': 'any'},
            {'src': static('icons/icon-512.png'), 'sizes': '512x512', 'type': 'image/png', 'purpose': 'any'},
            {'src': static('icons/icon-maskable-512.png'), 'sizes': '512x512', 'type': 'image/png',
             'purpose': 'maskable'},
            {'src': static('icons/icon.svg'), 'sizes': 'any', 'type': 'image/svg+xml', 'purpose': 'any'},
        ],
    }
    response = JsonResponse(data, content_type='application/manifest+json',
                            json_dumps_params={'ensure_ascii': False, 'indent': 2})
    response['Cache-Control'] = 'no-cache'
    return response


@require_GET
def service_worker(request):
    config = {
        'version': shell_version(),
        'offline': OFFLINE_URL,
        'shell': [OFFLINE_URL] + [static(name) for name in SHELL_FILES],
        'networkOnly': NETWORK_ONLY,
    }
    body = f'const CONFIG = {json.dumps(config)};\n' + SW_SOURCE.read_text(encoding='utf-8')
    response = HttpResponse(body, content_type='text/javascript; charset=utf-8')
    response['Cache-Control'] = 'no-cache'
    response['Service-Worker-Allowed'] = '/'
    return response


@require_GET
def offline(request):
    response = render(request, 'offline.html')
    response['Cache-Control'] = 'no-cache'
    return response


def root_file(request, name):
    path = finders.find(ROOT_FILES[name]) if name in ROOT_FILES else None
    if request.method not in ('GET', 'HEAD') or not path:
        return not_found(request)
    response = FileResponse(open(path, 'rb'))  # FileResponse schließt die Datei selbst
    response['Cache-Control'] = 'public, max-age=86400'
    return response

