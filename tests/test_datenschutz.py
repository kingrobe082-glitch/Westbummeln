"""Datenschutz: Konto löschen, Datenexport, Datenschutzseite, Sitzungen aufräumen, keine Daten in Logs."""
import json
import logging
from datetime import timedelta

import pytest
from django.contrib.sessions.backends.db import SessionStore
from django.contrib.sessions.models import Session
from django.utils import timezone

from datenschutz import services
from game import engine, rooms

PASSWORD = 'Funkgeraet-42'


def user_sessions(user_id):
    return services.sessions_of(user_id)


def second_device(game_client, name='Florian1', password=PASSWORD):
    other = game_client()
    assert other.account('login', name=name, password=password).status_code == 200
    return other


def oauth_client(game_client, django_user_model, name='Funk-1a2b3c4d', **fields):
    user = django_user_model(username=name, google_sub='google-123', **fields)
    user.set_unusable_password()
    user.save()
    client = game_client()
    client.client.force_login(user)
    return client, user


# ------------------------------------------------------------------ Konto löschen

def test_delete_with_wrong_password_keeps_account(player, django_user_model):
    response = player.account('delete_account', password='falsch-123')
    assert response.status_code == 400
    assert 'Passwort stimmt nicht' in response.json()['error']
    assert django_user_model.objects.filter(username='Florian1').exists()
    assert player.client.get('/account').json()['name'] == 'Florian1'


def test_delete_with_right_password(player, game_client, django_user_model):
    user = django_user_model.objects.get(username='Florian1')
    other = second_device(game_client)
    assert len(user_sessions(user.pk)) == 2

    response = player.account('delete_account', password=PASSWORD)

    assert response.status_code == 200
    assert response.json() == {'name': None, 'deleted': True}
    assert not django_user_model.objects.filter(pk=user.pk).exists()
    assert user_sessions(user.pk) == []
    # Das Sitzungscookie wird im Browser gelöscht.
    assert response.cookies['sessionid'].value == ''
    assert response.cookies['sessionid']['max-age'] == 0
    # Beide Geräte sind abgemeldet, eine neue Anmeldung geht nicht mehr.
    assert player.client.get('/account').json()['name'] is None
    assert other.client.get('/account').json()['name'] is None
    assert other.api('join').status_code == 401
    assert game_client().account('login', name='Florian1', password=PASSWORD).status_code == 400


def test_deleted_name_and_email_can_be_registered_again(player, game_client):
    player.account('delete_account', password=PASSWORD)
    response = game_client().account('register', name='Florian1', email='florian@example.com', password=PASSWORD)
    assert response.status_code == 200


def test_delete_oauth_account_needs_username(game_client, django_user_model):
    client, user = oauth_client(game_client, django_user_model)
    response = client.account('delete_account', confirm='Funk-falsch')
    assert response.status_code == 400
    assert 'Benutzernamen' in response.json()['error']
    assert client.account('delete_account', password='egal').status_code == 400
    assert django_user_model.objects.filter(pk=user.pk).exists()

    response = client.account('delete_account', confirm='  funk-1A2B3C4D ')  # Groß/klein und Leerzeichen egal
    assert response.status_code == 200
    assert not django_user_model.objects.filter(pk=user.pk).exists()
    assert user_sessions(user.pk) == []
    assert client.client.get('/account').json()['name'] is None


def test_delete_needs_login(game_client):
    response = game_client().account('delete_account', password=PASSWORD)
    assert response.status_code == 401


def test_delete_needs_csrf_token(player, django_user_model):
    response = player.post('/account', {'action': 'delete_account', 'password': PASSWORD}, csrf=False)
    assert response.status_code == 403
    assert django_user_model.objects.filter(username='Florian1').exists()


def test_delete_from_foreign_site_is_refused(player, django_user_model):
    response = player.client.post('/account', json.dumps({'action': 'delete_account', 'password': PASSWORD}),
                                  content_type='application/json',
                                  headers={'X-CSRFToken': player.token(), 'Origin': 'https://boese.example'})
    assert response.status_code == 403
    assert django_user_model.objects.filter(username='Florian1').exists()


def test_wrong_delete_password_counts_for_lockout(player, django_user_model):
    for _ in range(5):
        player.account('delete_account', password='falsch-123')
    response = player.account('delete_account', password=PASSWORD)
    assert response.status_code == 429
    assert django_user_model.objects.filter(username='Florian1').exists()


def test_delete_is_rate_limited(player, settings, django_user_model):
    settings.RATE_LIMITS = {**settings.RATE_LIMITS, 'login': '2/m'}
    player.account('delete_account', password='falsch-123')
    player.account('delete_account', password='falsch-124')
    response = player.account('delete_account', password=PASSWORD)
    assert response.status_code == 429
    assert django_user_model.objects.filter(username='Florian1').exists()


def test_delete_removes_player_from_all_rooms(player, game_client):
    # Raum 1: Florian1 ist Besitzer und fährt ein Fahrzeug, Ben spielt mit.
    player.create()
    own_room = player.room
    assert player.api('claim', vehicle='WB-3-HLF20').status_code == 200
    ben = game_client()
    ben.account('register', name='Ben', email='ben@example.com', password='Ben-Funkwort-1')
    ben.room = own_room
    ben.join()
    # Raum 2 gehört Cleo, Florian1 besetzt dort die Leitstelle.
    cleo = game_client()
    cleo.account('register', name='Cleo', email='cleo@example.com', password='Cleo-Funkwort-1')
    cleo.create()
    other = game_client()
    other.client = player.client  # dieselbe Sitzung, zweiter Spieler-Eintrag im anderen Raum
    other.room = cleo.room
    other.join()
    assert other.api('take_ls').status_code == 200
    # Raum 3 gehört Florian1 allein.
    lonely = game_client()
    lonely.client = player.client
    lonely.create()

    assert player.account('delete_account', password=PASSWORD).status_code == 200

    first = rooms.rooms[own_room]
    assert [p['name'] for p in first['players'].values()] == ['Ben']
    assert first['vehicles']['WB-3-HLF20']['owner'] is None
    assert first['owner_name'] == 'Ben'
    assert first['admin'] == ben.id
    messages = [entry['message'] for entry in first['radio']]
    assert 'Florian1 hat das Spiel verlassen. Florian WB 3 HLF 20 ist wieder frei.' in messages
    assert 'Ben verwaltet jetzt den Raum.' in messages
    second = rooms.rooms[cleo.room]
    assert [p['name'] for p in second['players'].values()] == ['Cleo']
    assert second['dispatcher'] is None
    assert lonely.room not in rooms.rooms
    # Ben spielt normal weiter und sieht Florian1 nicht mehr.
    state = ben.api('state').json()['state']
    assert [p['name'] for p in state['players']] == ['Ben']


def test_remove_account_clears_bans_and_kicks():
    result = rooms.create_room(1, 'Anna', False, 1000.0)
    r = rooms.rooms[result['room']]
    joined = rooms.handle(r, {'action': 'join'}, 2, 'Ben', False, 1000.0)
    rooms.handle(r, {'action': 'kick', 'id': result['id'], 'target': joined['id'], 'ban': True}, 1, 'Anna', False,
                 1001.0)
    assert 2 in r['banned'] and r['kicked']
    rooms.remove_account(2, 1002.0)
    assert r['banned'] == {} and r['kicked'] == {}
    assert r['owner_account'] == 1


def test_remove_account_keeps_radio_history():
    result = rooms.create_room(1, 'Anna', False, 1000.0)
    r = rooms.rooms[result['room']]
    joined = rooms.handle(r, {'action': 'join'}, 2, 'Ben', False, 1000.0)
    engine.handle(r, {'action': 'radio', 'id': joined['id'], 'message': 'Hier Ben, verstanden.'}, 2, 'Ben', False,
                  1001.0)
    rooms.remove_account(2, 1002.0)
    assert any(entry['message'] == 'Hier Ben, verstanden.' for entry in r['radio'])


# ------------------------------------------------------------------ Datenexport

def test_export_needs_login(game_client):
    response = game_client().client.get('/account/export')
    assert response.status_code == 401


def test_export_contains_account_data_without_secrets(player, game_client, django_user_model):
    second_device(game_client)
    player.create()
    user = django_user_model.objects.get(username='Florian1')

    response = player.client.get('/account/export')

    assert response.status_code == 200
    assert response['Content-Disposition'] == 'attachment; filename="westbummeln-meine-daten.json"'
    assert 'no-store' in response['Cache-Control']
    data = response.json()
    assert data['konto']['benutzername'] == 'Florian1'
    assert data['konto']['email'] == 'florian@example.com'
    assert data['konto']['passwort_gesetzt'] is True
    assert data['konto']['registriert_am'] and data['konto']['letzte_anmeldung']
    assert len(data['sitzungen']) == 2
    assert [s['dieses_geraet'] for s in data['sitzungen']].count(True) == 1
    assert data['spielraeume'] == [{'raumcode': player.room, 'raumbesitzer': True, 'im_raum_gesperrt': False,
                                    'spieler': {'name': 'Florian1', 'rolle': 'none', 'fahrzeug': None}}]
    # Weder Passwort-Hash (mit Salt) noch Sitzungsschlüssel stehen irgendwo in der Datei.
    body = response.content.decode()
    assert 'password' not in body and 'salt' not in body
    assert user.password not in body
    algorithm, _, salt, *_, hashed = user.password.split('$')  # scrypt$n$salt$r$p$hash
    assert algorithm == 'scrypt'
    assert salt not in body and hashed not in body
    for session in Session.objects.all():
        assert session.session_key not in body


def test_export_contains_moderation_data(player, django_user_model):
    from moderation.models import Ban, ModerationEvent

    user = django_user_model.objects.get(username='Florian1')
    moderator = django_user_model.objects.create(username='Mod')
    Ban.objects.create(user=user, created_by=moderator, reason='Spam im Funk', starts_at=timezone.now(),
                       lifted_at=timezone.now(), lifted_by=moderator)
    ModerationEvent.objects.create(actor=moderator, actor_name='Mod', action=ModerationEvent.KICK, target=user,
                                   target_name='Florian1', room_code='K7M2QX')
    response = player.client.get('/account/export')
    assert response.status_code == 200
    data = response.json()
    assert data['konto']['rolle'] == 'Spieler'
    assert [b['grund'] for b in data['sperren']] == ['Spam im Funk']
    assert data['sperren'][0]['aufgehoben_am']
    assert data['moderationsprotokoll'] == [
        {'zeit': data['moderationsprotokoll'][0]['zeit'], 'aktion': 'Spieler aus Raum entfernt', 'raum': 'K7M2QX'}]
    assert 'Mod' not in json.dumps(data['moderationsprotokoll'])  # keine Daten der Moderation


def test_delete_removes_bans_but_keeps_protocol_name(player, django_user_model):
    from moderation.models import Ban, ModerationEvent

    user = django_user_model.objects.get(username='Florian1')
    Ban.objects.create(user=user, reason='alt', starts_at=timezone.now(), lifted_at=timezone.now())
    ModerationEvent.objects.create(actor_name='System', action=ModerationEvent.KICK, target=user,
                                   target_name='Florian1')
    assert player.account('delete_account', password=PASSWORD).status_code == 200
    assert not Ban.objects.exists()
    event = ModerationEvent.objects.get()
    assert event.target is None and event.target_name == 'Florian1'


def test_export_of_oauth_account(game_client, django_user_model):
    client, _ = oauth_client(game_client, django_user_model)
    data = client.client.get('/account/export').json()
    assert data['konto']['google_id'] == 'google-123'
    assert data['konto']['passwort_gesetzt'] is False
    assert data['konto']['email'] is None


def test_export_is_rate_limited(player, settings):
    settings.RATE_LIMITS = {**settings.RATE_LIMITS, 'export': '1/m'}
    assert player.client.get('/account/export').status_code == 200
    assert player.client.get('/account/export').status_code == 429


# ------------------------------------------------------------------ Datenschutzseite

def test_privacy_page(client):
    response = client.get('/datenschutz')
    assert response.status_code == 200
    html = response.content.decode()
    assert 'Datenschutzhinweise' in html
    # Entscheidung von Lars: keine Angaben zum Verantwortlichen, keine sichtbaren Platzhalter.
    assert 'TODO' not in html and 'Verantwortlich' not in html and 'Kontakt' not in html
    assert 'Entwurf' not in html
    for number, title in enumerate(['Dein Konto', 'Anmeldung und Cookies', 'Im Spiel', 'Sprachfunk'], 1):
        assert f'<h2>{number}. {title}</h2>' in html
    assert 'Gültig 7 Tage' in html
    assert '<script' not in html


def test_privacy_page_shows_what_is_switched_on(client, monkeypatch):
    from accounts import services as account_services
    from integrations import discord

    monkeypatch.setattr(account_services, 'GOOGLE_CLIENT_ID', 'abc.apps.googleusercontent.com')
    monkeypatch.setattr(discord, 'WEBHOOK_OK', True)
    html = client.get('/datenschutz').content.decode()
    assert 'Anmeldung mit Google eingeschaltet' in html
    assert 'Funkspiegelung eingeschaltet' in html
    assert 'Anmeldung mit Discord ausgeschaltet' in html


def test_register_without_email(game_client, django_user_model):
    client = game_client()
    response = client.account('register', name='OhneMail', password=PASSWORD)
    assert response.status_code == 200
    assert django_user_model.objects.get(username='OhneMail').email is None
    assert game_client().account('register', name='OhneMail2', password=PASSWORD).status_code == 200


def test_register_form_asks_no_email(client):
    html = client.get('/').content.decode()
    assert 'accountEmail' not in html and 'autocomplete="email"' not in html


def test_start_page_asks_for_age_first(client):
    html = client.get('/').content.decode()
    gate = html.index('id="ageGate"')
    gate_script = html.index('js/agegate.js')
    assert gate < gate_script < html.index('<header>')  # läuft, bevor der Rest der Seite gezeichnet wird
    assert 'Bist du 18 Jahre oder älter?' in html
    assert 'id="ageYes"' in html and 'id="ageNo"' in html


def test_privacy_page_has_no_age_gate(client):
    html = client.get('/datenschutz').content.decode()
    assert 'ageGate' not in html
    assert 'nur für Personen ab 18 Jahren' in html


def test_privacy_links_on_start_page(client):
    html = client.get('/').content.decode()
    assert '<footer class="siteFooter small"><a href="/datenschutz">Datenschutz</a></footer>' in html
    assert 'Mit der Registrierung' in html
    assert 'id="exportData"' in html and 'id="deleteForm"' in html


# ------------------------------------------------------------------ Sitzungen aufräumen

def make_session(expires_in):
    store = SessionStore()
    store['x'] = 1
    store.create()
    Session.objects.filter(session_key=store.session_key).update(expire_date=timezone.now() + expires_in)
    return store.session_key


@pytest.mark.django_db
def test_cleanup_deletes_only_expired_sessions(monkeypatch):
    monkeypatch.setattr(services, '_last_cleanup', None)
    old = make_session(timedelta(seconds=-1))
    valid = make_session(timedelta(days=1))
    assert services.cleanup_if_due(now=5000.0) is True
    assert not Session.objects.filter(session_key=old).exists()
    assert Session.objects.filter(session_key=valid).exists()
    # Innerhalb einer Stunde läuft es nicht noch einmal.
    again = make_session(timedelta(seconds=-1))
    assert services.cleanup_if_due(now=5000.0 + 3599) is False
    assert Session.objects.filter(session_key=again).exists()
    assert services.cleanup_if_due(now=5000.0 + 3600) is True
    assert not Session.objects.filter(session_key=again).exists()


@pytest.mark.django_db
def test_cleanup_runs_after_requests(client, monkeypatch):
    monkeypatch.setattr(services, '_last_cleanup', None)
    old = make_session(timedelta(seconds=-1))
    assert client.get('/datenschutz').status_code == 200
    assert not Session.objects.filter(session_key=old).exists()


# ------------------------------------------------------------------ Keine persönlichen Daten in Logs

def test_account_actions_log_no_personal_data(game_client, caplog, capsys):
    caplog.set_level(logging.DEBUG)
    client = game_client()
    client.account('register', name='Geheimname', email='geheim@example.com', password=PASSWORD)
    client.account('login', name='geheim@example.com', password='falsch-123')
    client.client.get('/account/export')
    client.account('delete_account', password='falsch-123')
    client.account('delete_account', password=PASSWORD)
    output = caplog.text + ''.join(capsys.readouterr())
    assert 'Geheimname' not in output and 'geheim@example.com' not in output
