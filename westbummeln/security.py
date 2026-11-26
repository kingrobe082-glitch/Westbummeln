"""Schutzschicht für alle Anfragen: Client-IP hinter Renders Proxy, IP-Limits, Herkunftsprüfung,
Größenlimit und Header, die Django 5.2 nicht selbst setzt.

Zähler liegen im Django-Cache (LocMem). Das reicht, weil gunicorn genau einen Worker startet;
nach einem Neustart beginnen alle Zähler von vorn.
"""
import functools
import threading
import time
from urllib.parse import urlsplit

from django.conf import settings
from django.core.cache import cache

from westbummeln.views import json_reply

UNSAFE_METHODS = {'POST', 'PUT', 'PATCH', 'DELETE'}
PERIODS = {'s': 1, 'm': 60, 'h': 3600, 'd': 86400}
_limit_lock = threading.Lock()


def client_ip(request):
    """IP des Browsers. Hinter Renders Proxy steht sie in X-Forwarded-For.

    Jeder vertrauenswürdige Proxy hängt die Adresse, von der er die Anfrage bekam, rechts an.
    Bei TRUSTED_PROXY_COUNT = n ist deshalb der n-te Eintrag von rechts die echte Client-IP; alles
    weiter links kann der Client selbst gefälscht haben. Ohne Proxy (lokal) gilt REMOTE_ADDR."""
    count = settings.TRUSTED_PROXY_COUNT
    if count:
        hops = [hop.strip() for hop in request.META.get('HTTP_X_FORWARDED_FOR', '').split(',') if hop.strip()]
        if len(hops) >= count:
            return hops[-count]
    return request.META.get('REMOTE_ADDR', '') or 'unbekannt'


def parse_rate(rate):
    """'10/m' → (10, 60)."""
    amount, _, period = rate.partition('/')
    return int(amount), PERIODS[period]


def over_limit(request, scope):
    """Zählt die Anfrage für (scope, IP) und meldet True, wenn das Limit aus RATE_LIMITS überschritten ist.

    Festes Zeitfenster: höchstens `amount` Anfragen je angefangenem Fenster."""
    amount, period = parse_rate(settings.RATE_LIMITS[scope])
    window = int(time.time() // period)
    key = f'wb-limit:{scope}:{client_ip(request)}:{window}'
    with _limit_lock:
        count = cache.get(key, 0) + 1
        cache.set(key, count, period + 1)
    return count > amount


def too_many_requests():
    return json_reply({'error': 'Zu viele Anfragen. Bitte warte kurz und versuche es dann erneut.'}, 429)


def ip_limit(scope, response=too_many_requests):
    """Decorator: Bei überschrittenem IP-Limit antwortet die View mit `response()` statt zu laufen."""

    def decorator(view):
        @functools.wraps(view)
        def wrapper(request, *args, **kwargs):
            if over_limit(request, scope):
                return response()
            return view(request, *args, **kwargs)

        return wrapper

    return decorator


def same_origin(url, request):
    parts = urlsplit(url)
    return parts.scheme in ('http', 'https') and parts.netloc == request.get_host() and (
        parts.scheme == request.scheme)


def request_guard(get_response):
    """Vor jeder View: zu große Anfragen (413) und fremde Herkunft bei schreibenden Anfragen (403).

    Djangos CSRF-Prüfung bleibt die Hauptsicherung (Token + Origin). Diese Prüfung greift zusätzlich
    für jede View, auch wenn eine einmal csrf_exempt wäre, und lehnt fremde Seiten schon anhand von
    Sec-Fetch-Site ab, das Browser nicht fälschen lassen."""

    def middleware(request):
        size = request.META.get('CONTENT_LENGTH') or '0'
        if not size.isdigit() or int(size) > settings.DATA_UPLOAD_MAX_MEMORY_SIZE:
            return json_reply({'error': 'Anfrage zu groß.'}, 413)
        if request.method in UNSAFE_METHODS:
            fetch_site = request.headers.get('Sec-Fetch-Site', '')
            origin = request.headers.get('Origin') or request.headers.get('Referer') or ''
            foreign = fetch_site in ('cross-site', 'same-site') or (
                origin and origin != 'null' and not same_origin(origin, request))
            if foreign or origin == 'null':
                return json_reply({'error': 'Anfrage von fremder Seite abgelehnt.'}, 403)
        return get_response(request)

    return middleware


def security_headers(get_response):
    """Header, für die Django 5.2 keine Einstellung hat (CSP setzt django-csp)."""

    def middleware(request):
        response = get_response(request)
        response.setdefault('Permissions-Policy', settings.PERMISSIONS_POLICY)
        return response

    return middleware
