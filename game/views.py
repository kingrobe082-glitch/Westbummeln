import json
import re
import time

from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import ensure_csrf_cookie

from game import engine, rooms
from westbummeln.security import ip_limit
from westbummeln.views import json_reply, not_found, read_json

ROOM_RE = re.compile(r'[A-Z0-9-]{2,16}')


@ensure_csrf_cookie
def index(request):
    response = render(request, 'index.html')
    response['Cache-Control'] = 'no-cache'
    return response


@never_cache
@ip_limit('api')
def api(request):
    if request.method != 'POST':
        return not_found(request)
    if request.content_type != 'application/json':
        return json_reply({'error': 'JSON erforderlich'}, 415)
    try:
        data = read_json(request, 'Anfrage zu groß')
        action = data.get('action')
        code = str(data.get('room') or '').upper().strip()
        if action != 'create_room' and not ROOM_RE.fullmatch(code):
            raise ValueError('Ungültiger Raumcode')
        user = request.user
        if not user.is_authenticated:
            return json_reply({'error': 'Sitzung abgelaufen – bitte anmelden.'}, 401)
        # Besetzte Leitstelle übernehmen dürfen Moderatoren und Admins. Nur bei Bedarf prüfen:
        # /api wird von jedem Spieler mehrmals pro Sekunde abgefragt.
        can_take_over = action == 'take_ls' and user.has_perm('moderation.take_over_dispatch')
        now = time.time()
        with rooms.lock:
            rooms.sweep(now)
            if action == 'create_room':
                result = rooms.create_room(user.pk, user.username, can_take_over, now)
            else:
                r = rooms.get_room(code)
                engine.clean_offline(r, now)
                engine.update(r, now)
                result = rooms.handle(r, data, user.pk, user.username, can_take_over, now)
            # Antwort noch unter der Sperre serialisieren, damit kein anderer Thread dazwischenfunkt.
            return json_reply(result)
    except rooms.KickedError as error:
        return json_reply({'error': str(error), 'kicked': True}, 403)
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        return json_reply({'error': str(error)}, 400)
    except Exception:
        return json_reply({'error': 'Serverfehler'}, 500)


@never_cache
def developer(request):
    if request.method != 'GET':
        return not_found(request)
    if not request.user.has_perm('moderation.view_rooms'):
        return json_reply({'error': 'Zugang nur für Moderation und Admins.'}, 403)
    return json_reply(rooms.activity())
