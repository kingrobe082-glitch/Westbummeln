"""Fehlerseiten als JSON, wie beim alten Server. Das Frontend erwartet bei Fehlern {'error': …}."""
import json

from django.http import JsonResponse

MAX_BODY = 12000
BAD_REQUEST = 'Ungültige Anfrage.'


def json_reply(data, status=200):
    response = JsonResponse(data, status=status, json_dumps_params={'ensure_ascii': False})
    response['Cache-Control'] = 'no-store'
    return response


def not_found(request, exception=None):
    return json_reply({'error': 'Nicht gefunden'}, 404)


def server_error(request):
    return json_reply({'error': 'Serverfehler'}, 500)


def csrf_failure(request, reason=''):
    return json_reply({'error': 'Sicherheitsprüfung fehlgeschlagen. Bitte lade die Seite neu.'}, 403)


def read_json(request, too_big):
    """JSON-Körper lesen wie der alte Server: höchstens 12 000 Bytes, sonst ValueError(too_big)."""
    size = int(request.META.get('CONTENT_LENGTH') or '0')
    if not 0 < size <= MAX_BODY:
        raise ValueError(too_big)
    try:
        data = json.loads(request.body)
    except ValueError:  # auch UnicodeDecodeError; Pythons Fehlertext geht nicht an den Spieler
        raise ValueError(BAD_REQUEST) from None
    if not isinstance(data, dict):
        raise ValueError(BAD_REQUEST)
    return data


def account_id(request):
    """Konto-ID fürs Fehlerlog. Scheitert nie selbst, auch nicht, wenn die Datenbank weg ist."""
    try:
        user = request.user
        return user.pk if user.is_authenticated else None
    except Exception:
        return None
