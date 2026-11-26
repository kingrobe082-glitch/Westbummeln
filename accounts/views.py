"""Konto-Endpunkte. Das JSON entspricht dem alten Server, angemeldet wird jetzt per Django-Sitzung."""
import json
import secrets
import threading
import time
from collections import deque

from django.conf import settings
from django.contrib.auth import login, logout
from django.http import HttpResponseRedirect
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import ensure_csrf_cookie

from accounts import services
from integrations import discord
from westbummeln.views import json_reply, not_found, read_json

GOOGLE_NONCE_COOKIE = 'wb_google_nonce'
ATTEMPTS_PER_MINUTE = 90

# Höchstens 4 gleichzeitige Passwortprüfungen (scrypt braucht viel Speicher) und
# höchstens 90 Anmeldeversuche pro Minute für den ganzen Server, wie beim alten Server.
auth_slots = threading.BoundedSemaphore(4)
auth_attempts = deque()
attempts_lock = threading.Lock()


def too_many_attempts():
    now = time.monotonic()
    with attempts_lock:
        while auth_attempts and now - auth_attempts[0] >= 60:
            auth_attempts.popleft()
        if len(auth_attempts) >= ATTEMPTS_PER_MINUTE:
            return True
        auth_attempts.append(now)
    return False


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
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        return json_reply({'error': str(error)}, 400)
    except Exception:
        return json_reply({'error': 'Serverfehler'}, 500)


def account_status(request):
    user = request.user if request.user.is_authenticated else None
    name = user.username if user else None
    nonce = secrets.token_urlsafe(24) if services.GOOGLE_CLIENT_ID and not name else ''
    response = json_reply({
        'name': name,
        'googleClientId': services.GOOGLE_CLIENT_ID,
        'nonce': nonce,
        'developer': bool(user and user.is_staff),
        **discord.public_config(bool(name)),
    })
    if nonce:
        set_cookie(response, request, GOOGLE_NONCE_COOKIE, nonce, 600)
    return response


def account_action(request):
    data = read_json(request, 'Ungültige Anfragegröße')
    action = data.get('action')
    if action not in ('register', 'login', 'google', 'logout'):
        raise ValueError('Unbekannte Kontoaktion')
    if action == 'logout':
        logout(request)
        return json_reply({'name': None})
    if too_many_attempts():
        return json_reply({'error': 'Zu viele Anmeldeversuche. Bitte warte kurz.'}, 429)
    if not auth_slots.acquire(blocking=False):
        return json_reply({'error': 'Bitte versuche es gleich erneut.'}, 429)
    try:
        if action == 'google':
            user = services.login_with_google(data, request.COOKIES.get(GOOGLE_NONCE_COOKIE, ''))
        elif action == 'register':
            user = services.register(data)
        else:
            user = services.login_with_password(request, data)
    finally:
        auth_slots.release()
    login(request, user, backend='accounts.backends.UsernameOrEmailBackend')
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


@never_cache
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
    if too_many_attempts():
        return back('failed')
    try:
        discord_user = discord.complete_login(code, discord_redirect_uri(request))
    except discord.LoginError as error:
        return back(error.code)
    try:
        user = services.login_with_discord(discord_user)
    except ValueError:
        return back('failed')
    login(request, user, backend='accounts.backends.UsernameOrEmailBackend')
    response = redirect('/')
    response.delete_cookie(discord.STATE_COOKIE, samesite='Lax')
    return response
