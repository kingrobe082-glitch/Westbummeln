"""Welle 2A Sicherheit: IP-Limits, Login-Sperre, Header, Herkunftsprüfung, Passwort ändern,
„Überall abmelden“ und Sitzungs-Cookies."""
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from django.contrib.sessions.models import Session
from django.test import RequestFactory

import westbummeln.security
from accounts import lockout
from westbummeln.security import client_ip

pytestmark = pytest.mark.django_db
ROOT = Path(__file__).resolve().parent.parent
LIMIT_MESSAGE = 'Zu viele Anfragen. Bitte warte kurz und versuche es dann erneut.'


@pytest.fixture
def fixed_limit_window(monkeypatch):
    """Die IP-Limits zählen in festen Zeitfenstern (int(time // Periode)). Fällt eine Testserie
    zufällig über eine Fenstergrenze, beginnt die Zählung neu und der Test schlägt sporadisch fehl.
    Deshalb steht die Uhr des Limiters in den Limit-Tests still (nicht global: andere Tests
    stellen die Uhr selbst vor und brauchen dann neue Fenster)."""
    monkeypatch.setattr(westbummeln.security, 'time', SimpleNamespace(time=lambda: 1_800_000_000.0))


def post_from(client, path, data, ip='10.0.0.1', **extra):
    """POST wie das Frontend, aber von einer bestimmten IP."""
    return client.client.post(path, json.dumps(data), content_type='application/json',
                              headers={'X-CSRFToken': client.token()}, REMOTE_ADDR=ip, **extra)


def login(client, name, password, ip='10.0.0.1'):
    return post_from(client, '/account', {'action': 'login', 'name': name, 'password': password}, ip)


# ------------------------------------------------------------------ Client-IP


def test_client_ip_uses_last_proxy_hop(settings):
    request = RequestFactory().get('/', REMOTE_ADDR='10.1.1.1', HTTP_X_FORWARDED_FOR='6.6.6.6, 5.5.5.5')
    settings.TRUSTED_PROXY_COUNT = 1
    assert client_ip(request) == '5.5.5.5'  # 6.6.6.6 hat der Client selbst eingetragen
    settings.TRUSTED_PROXY_COUNT = 0
    assert client_ip(request) == '10.1.1.1'


# ------------------------------------------------------------------- IP-Limits


@pytest.mark.usefixtures("fixed_limit_window")
def test_login_limit_is_per_ip(game_client):
    client = game_client()
    for number in range(10):
        assert login(client, f'niemand{number}', 'falsch123').status_code == 400
    response = login(client, 'niemand99', 'falsch123')
    assert response.status_code == 429
    assert response.json() == {'error': LIMIT_MESSAGE}
    # Eine andere IP ist davon nicht betroffen (früher sperrte ein Angreifer alle aus).
    assert login(client, 'niemand99', 'falsch123', ip='10.0.0.2').status_code == 400


@pytest.mark.usefixtures("fixed_limit_window")
def test_register_limit(game_client):
    client = game_client()
    for number in range(5):
        response = post_from(client, '/account', {'action': 'register', 'name': f'Neu{number}',
                                                  'email': f'neu{number}@example.com', 'password': 'Funkgeraet-42'})
        assert response.status_code == 200
    response = post_from(client, '/account', {'action': 'register', 'name': 'Neu9',
                                              'email': 'neu9@example.com', 'password': 'Funkgeraet-42'})
    assert response.status_code == 429


@pytest.mark.usefixtures("fixed_limit_window")
def test_api_limit_returns_json(player, settings):
    settings.RATE_LIMITS = {**settings.RATE_LIMITS, 'api': '3/m'}
    player.create()
    for _ in range(2):
        assert player.api('state').status_code == 200
    response = player.api('state')
    assert response.status_code == 429
    assert response.json() == {'error': LIMIT_MESSAGE}


def test_api_limit_is_generous_enough_for_polling(settings):
    amount, period = (int(part) if part.isdigit() else part for part in settings.RATE_LIMITS['api'].split('/'))
    # Spielstand alle 1,5 s + Sprachfunk alle 1,7 s ≈ 75 Anfragen/Minute für einen Spieler.
    assert period == 'm' and amount >= 3 * 75


@pytest.mark.usefixtures("fixed_limit_window")
def test_discord_callback_limit(client, settings):
    settings.RATE_LIMITS = {**settings.RATE_LIMITS, 'discord': '0/m'}
    response = client.get('/auth/discord/callback?code=x&state=y')
    assert response.status_code == 302
    assert response['Location'] == '/?login_error=failed'


# ---------------------------------------------------------------- Login-Sperre


def test_lockout_after_five_failures_also_blocks_right_password(player, game_client):
    client = game_client()
    for _ in range(5):
        assert login(client, 'Florian1', 'falsch123').status_code == 400
    response = login(client, 'Florian1', 'Funkgeraet-42')
    assert response.status_code == 429
    assert response.json() == {'error': lockout.LOCKED_MESSAGE}
    # Der Besitzer an seiner eigenen IP ist nicht ausgesperrt.
    assert login(client, 'Florian1', 'Funkgeraet-42', ip='10.0.0.2').status_code == 200


def test_lockout_message_same_for_unknown_account(player, game_client):
    client = game_client()
    for name in ('Florian1', 'GibtEsNicht'):
        for _ in range(5):
            login(client, name, 'falsch123')
    known = login(client, 'Florian1', 'falsch123')
    unknown = login(client, 'GibtEsNicht', 'falsch123')
    assert known.status_code == unknown.status_code == 429
    assert known.json() == unknown.json()


def test_lockout_cannot_be_bypassed_with_spelling_or_email(player, game_client):
    client = game_client()
    for name in ('Florian1', 'florian1', 'FLORIAN1', 'florian@example.com', ' Florian1 '):
        login(client, name, 'falsch123')
    assert login(client, 'fLoRiAn1', 'Funkgeraet-42').status_code == 429


def test_lockout_grows_and_resets_on_success(player, game_client, monkeypatch):
    clock = [1_000_000.0]
    monkeypatch.setattr(lockout.time, 'time', lambda: clock[0])
    client = game_client()

    def fail_five_times():
        for _ in range(5):
            login(client, 'Florian1', 'falsch123')

    fail_five_times()
    clock[0] += 59
    assert login(client, 'Florian1', 'Funkgeraet-42').status_code == 429
    clock[0] += 2  # 1 Minute vorbei
    fail_five_times()
    clock[0] += 4 * 60
    assert login(client, 'Florian1', 'Funkgeraet-42').status_code == 429
    clock[0] += 61  # 5 Minuten vorbei
    fail_five_times()
    clock[0] += 14 * 60
    assert login(client, 'Florian1', 'Funkgeraet-42').status_code == 429
    clock[0] += 61  # 15 Minuten vorbei
    assert login(client, 'Florian1', 'Funkgeraet-42').status_code == 200
    # Erfolg setzt zurück: wieder erst ab 5 Fehlversuchen und nur 1 Minute.
    for _ in range(4):
        login(client, 'Florian1', 'falsch123')
    assert login(client, 'Florian1', 'Funkgeraet-42').status_code == 200


def test_unknown_account_still_hashes_password(game_client, monkeypatch, django_user_model):
    calls = []
    original = django_user_model.set_password
    monkeypatch.setattr(django_user_model, 'set_password', lambda user, raw: calls.append(raw) or original(user, raw))
    assert login(game_client(), 'GibtEsNicht', 'falsch123').status_code == 400
    assert calls == ['falsch123']


# -------------------------------------------------------------------- Header


def test_security_headers(client):
    response = client.get('/')
    csp = response['Content-Security-Policy']
    for directive in ("default-src 'self'", "script-src 'self' https://accounts.google.com/gsi/client",
                      "style-src 'self' 'unsafe-inline' https://accounts.google.com/gsi/style",
                      "frame-ancestors 'none'", "object-src 'none'",
                      "connect-src 'self' https://accounts.google.com/gsi/", "img-src 'self' data:"):
        assert directive in csp
    directives = dict(part.strip().split(' ', 1) for part in csp.split(';'))
    assert [name for name, value in directives.items() if 'unsafe' in value] == ['style-src']  # nie bei Skripten
    assert response['X-Content-Type-Options'] == 'nosniff'
    assert response['Referrer-Policy'] == 'strict-origin-when-cross-origin'
    assert response['Permissions-Policy'].startswith('microphone=(self), camera=()')
    assert response['Cross-Origin-Opener-Policy'] == 'same-origin-allow-popups'
    assert response['X-Frame-Options'] == 'DENY'
    assert 'Strict-Transport-Security' not in response


def test_headers_also_on_json_errors(client):
    response = client.post('/account', 'x' * 20000, content_type='application/json')
    assert response.status_code == 413
    assert 'Content-Security-Policy' in response and 'Permissions-Policy' in response


def test_hsts_only_over_https(client, settings):
    settings.SECURE_HSTS_SECONDS = 86400
    assert 'Strict-Transport-Security' not in client.get('/')
    assert client.get('/', secure=True)['Strict-Transport-Security'] == 'max-age=86400'


def test_index_has_no_inline_scripts_or_handlers(client):
    html = client.get('/').content.decode()
    assert '<script>' not in html and '<script >' not in html
    assert ' onclick=' not in html and ' onchange=' not in html and ' onsubmit=' not in html


# ----------------------------------------------------------- Herkunftsprüfung


@pytest.mark.parametrize('headers', [
    {'Origin': 'https://boese.example'},
    {'Origin': 'null'},
    {'Referer': 'https://boese.example/seite'},
    {'Sec-Fetch-Site': 'cross-site'},
    {'Sec-Fetch-Site': 'same-site'},
    {'Origin': 'https://testserver'},  # anderes Schema als die Anfrage (http)
])
def test_foreign_origin_is_refused(player, headers):
    response = player.client.post('/api', json.dumps({'action': 'join', 'room': 'WB'}), content_type='application/json',
                                  headers={'X-CSRFToken': player.token(), **headers})
    assert response.status_code == 403
    assert response.json() == {'error': 'Anfrage von fremder Seite abgelehnt.'}


def test_own_origin_is_accepted(player):
    response = player.client.post('/api', json.dumps({'action': 'create_room'}), content_type='application/json',
                                  headers={'X-CSRFToken': player.token(), 'Origin': 'http://testserver',
                                           'Sec-Fetch-Site': 'same-origin'})
    assert response.status_code == 200


def test_json_content_type_still_required(player):
    response = player.client.post('/api', 'action=join', content_type='application/x-www-form-urlencoded',
                                  headers={'X-CSRFToken': player.token()})
    assert response.status_code == 415


def test_too_large_body_is_refused(player):
    response = player.post('/api', {'action': 'state', 'room': 'WB', 'padding': 'x' * 17000})
    assert response.status_code == 413
    assert response.json() == {'error': 'Anfrage zu groß.'}


# ---------------------------------------------------- Passwort ändern / abmelden


def second_device(game_client, name='Florian1', password='Funkgeraet-42'):
    other = game_client()
    assert other.account('login', name=name, password=password).status_code == 200
    return other


def test_change_password_ends_other_sessions(player, game_client):
    other = second_device(game_client)
    response = player.account('change_password', old_password='Funkgeraet-42', new_password='Neues-Funkwort-7')
    assert response.status_code == 200
    assert player.client.get('/account').json()['name'] == 'Florian1'  # dieses Gerät bleibt angemeldet
    assert other.client.get('/account').json()['name'] is None
    assert other.api('join').status_code == 401
    assert game_client().account('login', name='Florian1', password='Funkgeraet-42').status_code == 400
    assert game_client().account('login', name='Florian1', password='Neues-Funkwort-7').status_code == 200


def test_change_password_rotates_session_key(player):
    before = player.client.cookies['sessionid'].value
    player.account('change_password', old_password='Funkgeraet-42', new_password='Neues-Funkwort-7')
    assert player.client.cookies['sessionid'].value != before
    assert not Session.objects.filter(session_key=before).exists()


@pytest.mark.parametrize('fields, message', [
    ({'old_password': 'falsch123', 'new_password': 'Neues-Funkwort-7'}, 'Das bisherige Passwort stimmt nicht.'),
    ({'old_password': 'Funkgeraet-42', 'new_password': 'passwort'}, 'zu üblich'),
    ({'old_password': 'Funkgeraet-42', 'new_password': 'kurz'}, '8 Zeichen'),
])
def test_change_password_errors(player, fields, message):
    response = player.account('change_password', **fields)
    assert response.status_code == 400
    assert message in response.json()['error']


def test_change_password_needs_login(game_client):
    response = game_client().account('change_password', old_password='a' * 8, new_password='b' * 8)
    assert response.status_code == 401


def test_change_password_without_password_account(game_client, django_user_model):
    user = django_user_model(username='Funk-google')
    user.set_unusable_password()
    user.save()
    client = game_client()
    client.client.force_login(user)
    response = client.account('change_password', old_password='egal1234', new_password='Neues-Funkwort-7')
    assert response.status_code == 400
    assert 'Google oder Discord' in response.json()['error']
    assert client.client.get('/account').json()['hasPassword'] is False


def test_wrong_old_password_counts_for_lockout(player):
    for _ in range(5):
        player.account('change_password', old_password='falsch123', new_password='Neues-Funkwort-7')
    response = player.account('change_password', old_password='Funkgeraet-42', new_password='Neues-Funkwort-7')
    assert response.status_code == 429


def test_logout_everywhere(player, game_client):
    other = second_device(game_client)
    assert player.account('logout_all').json() == {'name': None}
    assert player.client.get('/account').json()['name'] is None
    assert other.client.get('/account').json()['name'] is None
    # Neu anmelden geht danach ganz normal.
    assert second_device(game_client).client.get('/account').json()['name'] == 'Florian1'


def test_register_rejects_common_password(game_client):
    response = game_client().account('register', name='Neu', email='neu@example.com', password='passwort1')
    assert response.status_code == 400
    assert 'zu üblich' in response.json()['error']


# ------------------------------------------------------------ Sitzungs-Cookie


def test_login_rotates_session(player, game_client):
    old = player.client.cookies['sessionid'].value
    assert player.account('login', name='Florian1', password='Funkgeraet-42').status_code == 200
    new = player.client.cookies['sessionid'].value
    assert new != old
    assert not Session.objects.filter(session_key=old).exists()


def test_session_fixation_is_prevented(player, game_client):
    client = game_client()
    session = client.client.session
    session['vorher'] = 1
    session.save()
    planted = session.session_key
    client.client.cookies['sessionid'] = planted
    assert client.account('login', name='Florian1', password='Funkgeraet-42').status_code == 200
    assert client.client.cookies['sessionid'].value != planted


def test_session_cookie_flags(player, game_client, settings):
    settings.SESSION_COOKIE_SECURE = True
    response = game_client().account('login', name='Florian1', password='Funkgeraet-42')
    cookie = response.cookies['sessionid']
    assert cookie['httponly'] and cookie['secure']
    assert cookie['samesite'] == 'Lax'


def test_secure_settings_in_production():
    """In Produktion (eigener Prozess, weil die Einstellungen beim Import feststehen)."""
    code = ('import django; django.setup(); from django.conf import settings as s; '
            'print(s.SESSION_COOKIE_SECURE, s.CSRF_COOKIE_SECURE, s.SESSION_COOKIE_HTTPONLY, '
            's.SESSION_COOKIE_SAMESITE, s.TRUSTED_PROXY_COUNT)')
    keep = {k: v for k, v in os.environ.items()
            if k not in ('DATABASE_URL', 'SECRET_KEY', 'RENDER', 'TRUSTED_PROXY_COUNT')}
    env = {**keep, 'DJANGO_SETTINGS_MODULE': 'westbummeln.settings', 'RENDER': 'true', 'DJANGO_ENV': 'prod',
           'SECRET_KEY': 'x' * 50, 'DATABASE_URL': 'postgres://u:p@db:5432/wb', 'ALLOWED_HOSTS': 'example.org'}
    result = subprocess.run([sys.executable, '-c', code], cwd=ROOT, env=env, capture_output=True, text=True)
    assert result.stdout.split() == ['True', 'True', 'True', 'Lax', '1'], result.stderr
