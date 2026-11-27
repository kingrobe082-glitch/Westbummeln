"""HTTP-Endpunkte wie das Frontend sie benutzt (mit CSRF-Prüfung)."""
import json

import pytest
from django.test import Client

from game import rooms
from tests.helpers import make_moderator


@pytest.mark.django_db
def test_index_page_sets_csrf_cookie_and_links_static_files():
    client = Client()
    response = client.get('/')
    assert response.status_code == 200
    assert 'csrftoken' in response.cookies
    html = response.content.decode()
    for asset in ('/static/css/app.css', '/static/js/app.js', '/static/js/game.js', '/static/js/voice.js',
                  '/static/js/account.js', '/static/js/fahrzeuge.js', '/static/css/fahrzeuge.css',
                  '/static/js/gf-layout.js', '/static/css/gf-layout.css',
                  '/static/karte.webp'):
        assert asset in html
    assert client.get('/index.html').status_code == 200


def test_health_check_ignores_host_header():
    response = Client().get('/healthz', HTTP_HOST='10.0.0.7:10000')
    assert response.status_code == 200
    assert response.content == b'ok'


@pytest.mark.django_db
def test_unknown_path_is_json_404():
    response = Client().get('/gibtsnicht')
    assert response.status_code == 404
    assert response.json() == {'error': 'Nicht gefunden'}


@pytest.mark.django_db
def test_account_status_logged_out(game_client):
    data = game_client().client.get('/account').json()
    assert data['name'] is None
    assert data['developer'] is False
    assert data['discordLogin'] is False
    assert set(data) >= {'name', 'googleClientId', 'nonce', 'developer', 'discordLogin', 'discordVoiceUrl'}
    assert data['publicRoom'] == ''


@pytest.mark.django_db
def test_public_room_is_announced(game_client, monkeypatch):
    """Ist DISCORD_ROOM gesetzt, zeigt die Startseite einen Knopf für diesen festen Raum."""
    from integrations import discord
    monkeypatch.setattr(discord, 'ROOM', 'WESTBUMMELN')
    monkeypatch.setattr(discord, 'ROOM_OK', True)
    assert game_client().client.get('/account').json()['publicRoom'] == 'WESTBUMMELN'


def test_register_logs_in(player):
    data = player.client.get('/account').json()
    assert data['name'] == 'Florian1'


def test_login_with_username_and_with_email(player, game_client):
    for name in ('florian1', 'FLORIAN@example.com'):
        client = game_client()
        response = client.account('login', name=name, password='Funkgeraet-42')
        assert response.status_code == 200, response.json()
        assert response.json() == {'name': 'Florian1'}
        assert client.client.get('/account').json()['name'] == 'Florian1'


def test_wrong_password(player, game_client):
    response = game_client().account('login', name='Florian1', password='falsch123')
    assert response.status_code == 400
    assert response.json() == {'error': 'Benutzername oder Passwort stimmt nicht.'}


def test_register_errors_are_german(player, game_client, settings):
    settings.RATE_LIMITS = {**settings.RATE_LIMITS, 'register': '100/h'}  # hier geht es um die Meldungen
    client = game_client()
    cases = [
        ({'name': 'ab', 'email': 'a@b.de', 'password': 'Funkgeraet-42'},
         'Benutzername: 3–24 Buchstaben, Zahlen, Unterstriche oder Bindestriche.'),
        ({'name': 'Neu', 'email': 'a@b.de', 'password': 'kurz'}, 'Das Passwort braucht mindestens 8 Zeichen.'),
        ({'name': 'Neu', 'email': 'kaputt', 'password': 'Funkgeraet-42'}, 'Bitte gib eine gültige E-Mail-Adresse ein.'),
        ({'name': 'Neu', 'email': 'florian@example.com', 'password': 'Funkgeraet-42'},
         'Diese E-Mail-Adresse ist bereits registriert.'),
        ({'name': 'FLORIAN1', 'email': 'neu@example.com', 'password': 'Funkgeraet-42'},
         'Dieser Benutzername oder diese E-Mail ist bereits vergeben.'),
    ]
    for fields, message in cases:
        response = client.account('register', **fields)
        assert response.status_code == 400
        assert response.json() == {'error': message}


def test_logout(player):
    assert player.account('logout').json() == {'name': None}
    assert player.client.get('/account').json()['name'] is None


def test_post_without_csrf_token_is_refused(player):
    response = player.post('/api', {'action': 'join', 'room': 'WB'}, csrf=False)
    assert response.status_code == 403
    assert 'Sicherheitsprüfung' in response.json()['error']


def test_api_requires_login(game_client):
    client = game_client()
    response = client.api('join')
    assert response.status_code == 401
    assert response.json() == {'error': 'Sitzung abgelaufen – bitte anmelden.'}


def test_api_requires_json(player):
    response = player.client.post('/api', 'x=1', content_type='application/x-www-form-urlencoded',
                                  headers={'X-CSRFToken': player.token()})
    assert response.status_code == 415
    assert response.json() == {'error': 'JSON erforderlich'}


def test_api_rejects_bad_room_code(player):
    player.room = 'ä'
    response = player.api('join')
    assert response.status_code == 400
    assert response.json() == {'error': 'Ungültiger Raumcode'}


def test_api_rejects_large_body(player):
    response = player.post('/api', {'action': 'radio', 'message': 'x' * 13000})
    assert response.json() == {'error': 'Anfrage zu groß'}


def test_game_round_over_http(player, game_client):
    state = player.create()
    assert state['players'][0]['name'] == 'Florian1'
    rooms.rooms[player.room]['weather_mode'] = 'manual'
    # Allein im Raum würde die KI-Leitstelle sofort nach AAO alarmieren (evtl. auch WB-3-HLF20).
    rooms.rooms[player.room]['ai_last'] = 10 ** 12

    second = game_client()
    second.account('register', name='Zweite', email='zwei@example.com', password='Funkgeraet-42')
    second.room = player.room
    second.join()

    assert player.api('take_ls').status_code == 200
    assert second.api('claim', vehicle='WB-3-HLF20').status_code == 200
    response = player.api('incident', title='F1 · Kleinbrand', address='Marktplatz')
    incident = response.json()['state']['incidents'][-1]
    response = player.api('dispatch', incident=incident['id'], vehicle='WB-3-HLF20')
    vehicle = next(v for v in response.json()['state']['vehicles'] if v['id'] == 'WB-3-HLF20')
    assert vehicle['phase'] == 'anfahrt'

    response = second.api('radio', message='Florian WB 3 HLF 20 auf Anfahrt')
    last = response.json()['state']['radio'][-1]
    assert last == {**last, 'author': 'Zweite', 'kind': 'funk', 'call': 'Florian WB 3 HLF 20'}

    response = player.api('dispatch', incident=incident['id'], vehicle='WB-3-HLF20')
    assert response.status_code == 400
    assert response.json() == {'error': 'Fahrzeug ist nicht frei'}

    state = second.api('state').json()['state']
    assert state['dispatcher'] == player.id
    assert json.dumps(state, ensure_ascii=False)


def test_player_id_from_other_account_is_rejected(player, game_client):
    player.create()
    other = game_client()
    other.account('register', name='Fremd', email='fremd@example.com', password='Funkgeraet-42')
    other.room = player.room
    other.id = player.id
    response = other.api('state')
    assert response.json() == {'error': 'Sitzung abgelaufen – bitte neu beitreten'}


def test_developer_view(player, django_user_model):
    assert player.client.get('/developer').status_code == 403
    make_moderator(django_user_model.objects.get(username='Florian1'))
    player.create()
    assert player.client.get('/developer').json() == {'rooms': 1, 'players': 1, 'rooms_total': 1}


def test_discord_login_disabled_redirects():
    response = Client().get('/auth/discord')
    assert response.status_code == 302
    assert response['Location'] == '/?login_error=off'
