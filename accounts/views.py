"""Konto-Endpunkte. Das JSON entspricht dem alten Server, angemeldet wird jetzt per Django-Sitzung."""
import json
import secrets
import threading

from django.conf import settings
from django.contrib.auth import login, logout
from django.http import HttpResponseRedirect
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import ensure_csrf_cookie

from accounts import services
from accounts.lockout import LoginLockedError
from integrations import discord
from moderation.bans import check_not_banned
from moderation.errors import BannedError
from moderation.roles import role_of
from westbummeln.security import ip_limit, over_limit, too_many_requests
from westbummeln.views import json_reply, not_found, read_json

GOOGLE_NONCE_COOKIE = 'wb_google_nonce'
ACTIONS = ('register', 'login', 'google', 'logout', 'change_password', 'logout_all')
# Welches IP-Limit aus settings.RATE_LIMITS für welche Kontoaktion gilt.
ACTION_LIMITS = {'login': 'login', 'google': 'login', 'change_password': 'login', 'register': 'register'}

# Höchstens 4 gleichzeitige Passwortprüfungen: scrypt braucht viel Speicher.
auth_slots = threading.BoundedSemaphore(4)


def start_session(request, user):
    """Anmelden mit immer neuem Sitzungsschlüssel. Djangos login() behält den Schlüssel, wenn dasselbe
    Konto schon angemeldet war; wie beim alten Server bekommt jeder Login trotzdem einen neuen.

    Gesperrte Konten (Passwort, Google, Discord) scheitern hier mit BannedError."""
    check_not_banned(user)
    old_key = request.session.session_key
    login(request, user, backend='accounts.backends.UsernameOrEmailBackend')
    if request.session.session_key == old_key:
        request.session.cycle_key()


def set_cookie(response, request, name, value, max_age):
    response.set_cookie(name, value, max_age=max_age, httponly=True, samesite='Lax',
                        secure=request.is_secure() or settings.SECURE_COOKIES)


@never_cache
@ensure_csrf_cookie
def account(request):
    if request.method == 'GET':
        return account_status(request)
    if request.method != 'POST':
        return not_found(request)
    if request.content_type != 'application/json':
        return json_reply({'error': 'JSON erforderlich'}, 415)
    try:
        return account_action(request)
    except LoginLockedError as error:
        return json_reply({'error': str(error)}, 429)
    except BannedError as error:
        return json_reply({'error': str(error), 'banned': True}, 403)
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        return json_reply({'error': str(error)}, 400)
    except Exception:
        return json_reply({'error': 'Serverfehler'}, 500)


def account_status(request):
    user = request.user if request.user.is_authenticated else None
    name = user.username if user else None
    nonce = secrets.token_urlsafe(24) if services.GOOGLE_CLIENT_ID and not name else ''
    data = {
        'name': name,
        'googleClientId': services.GOOGLE_CLIENT_ID,
        'nonce': nonce,
        # „developer“ heißt fürs Frontend: darf eine besetzte Leitstelle übernehmen (Moderator, Admin).
        'developer': bool(user and user.has_perm('moderation.take_over_dispatch')),
        'role': role_of(user),
        'staff': bool(user and user.is_staff),
        'hasPassword': bool(user and user.has_usable_password()),
        **discord.public_config(bool(name)),
    }
    if not name and 'login_notice' in request.session:
        data['loginNotice'] = request.session.pop('login_notice')
    response = json_reply(data)
    if nonce:
        set_cookie(response, request, GOOGLE_NONCE_COOKIE, nonce, 600)
    return response


def account_action(request):
    data = read_json(request, 'Ungültige Anfragegröße')
    action = data.get('action')
    if action not in ACTIONS:
        raise ValueError('Unbekannte Kontoaktion')
    if action == 'logout':
        logout(request)
        return json_reply({'name': None})
    if action in ('change_password', 'logout_all') and not request.user.is_authenticated:
        return json_reply({'error': 'Sitzung abgelaufen – bitte anmelden.'}, 401)
    if action == 'logout_all':
        services.logout_everywhere(request.user)
        logout(request)
        return json_reply({'name': None})
    if over_limit(request, ACTION_LIMITS[action]):
        return too_many_requests()
    if not auth_slots.acquire(blocking=False):
        return json_reply({'error': 'Bitte versuche es gleich erneut.'}, 429)
    try:
        if action == 'change_password':
            user = services.change_password(request, data)
            return json_reply({'name': user.username})
        if action == 'google':
            user = services.login_with_google(data, request.COOKIES.get(GOOGLE_NONCE_COOKIE, ''))
        elif action == 'register':
            user = services.register(data)
        else:
            user = services.login_with_password(request, data)
    finally:
        auth_slots.release()
    start_session(request, user)
    response = json_reply({'name': user.username})
    if action == 'google':
        response.delete_cookie(GOOGLE_NONCE_COOKIE, samesite='Lax')
    return response


def redirect(url):
    response = HttpResponseRedirect(url)
    response['Cache-Control'] = 'no-store'
    return response


def discord_redirect_uri(request):
    return discord.redirect_uri(request.get_host(), request.is_secure() or settings.SECURE_COOKIES)


@never_cache
def discord_start(request):
    if not discord.login_enabled():
        return redirect('/?login_error=off')
    state = secrets.token_urlsafe(24)
    response = redirect(discord.authorize_url(state, discord_redirect_uri(request)))
    set_cookie(response, request, discord.STATE_COOKIE, state, 600)
    return response


def discord_too_many():
    response = redirect('/?login_error=failed')
    response.delete_cookie(discord.STATE_COOKIE, samesite='Lax')
    return response


@never_cache
@ip_limit('discord', discord_too_many)
def discord_callback(request):
    def back(code):
        response = redirect('/?login_error=' + code)
        response.delete_cookie(discord.STATE_COOKIE, samesite='Lax')
        return response

    if not discord.login_enabled():
        return back('off')
    code = request.GET.get('code', '')
    state = request.GET.get('state', '')
    if 'error' in request.GET and not code:
        return back('cancel')
    expected = request.COOKIES.get(discord.STATE_COOKIE, '')
    if not code or not state or not expected or not secrets.compare_digest(state, expected):
        return back('state')
    try:
        discord_user = discord.complete_login(code, discord_redirect_uri(request))
    except discord.LoginError as error:
        return back(error.code)
    try:
        user = services.login_with_discord(discord_user)
        start_session(request, user)
    except BannedError as error:
        # Die Meldung mit Sperrende holt sich die Seite über GET /account (loginNotice).
        request.session['login_notice'] = str(error)
        return back('banned')
    except ValueError:
        return back('failed')
    response = redirect('/')
    response.delete_cookie(discord.STATE_COOKIE, samesite='Lax')
    return response
