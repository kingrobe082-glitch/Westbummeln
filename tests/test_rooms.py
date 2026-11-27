"""Raumcodes, Besitzer, Limits, Ablauf, Kick/Sperre und Rejoin (game.rooms)."""
import re

import pytest

from game import engine, rooms
from integrations import discord
from tests.helpers import make_moderator

NOW = 1_000_000.0
EXPIRY = engine.OFFLINE_TIMEOUT + 1800


def create(account=1, name='Anna', now=NOW):
    result = rooms.create_room(account, name, False, now)
    return rooms.rooms[result['room']], result['id']


def act(r, who, pid, action, now=NOW, name='Anna', **data):
    """Wie game.views.api: erst Offline-Spieler aufräumen, dann die Aktion ausführen (`who` = Konto-ID)."""
    engine.clean_offline(r, now)
    return rooms.handle(r, {'action': action, 'id': pid, **data}, who, name, False, now)


def join(r, account, name, now=NOW):
    return act(r, account, None, 'join', now, name)['id']


# ------------------------------------------------------------------ Codes und unbekannte Räume

def test_created_code_is_six_readable_characters():
    r, pid = create()
    assert re.fullmatch(r'[ABCDEFGHJKLMNPQRSTUVWXYZ23456789]{6}', r['code'])
    assert r['owner_account'] == 1
    assert r['admin'] == pid
    assert list(r['players']) == [pid]


def test_code_generation_skips_existing_codes(monkeypatch):
    rooms.rooms['AAAAAA'] = engine.new_room('AAAAAA')
    letters = iter('A' * 6 + 'B' * 6)
    monkeypatch.setattr(rooms.secrets, 'choice', lambda alphabet: next(letters))
    assert rooms.new_code() == 'BBBBBB'


def test_unknown_room_is_not_created():
    with pytest.raises(ValueError, match='Raum nicht gefunden'):
        rooms.get_room('WESTBUMMELN')
    assert rooms.rooms == {}


def test_create_room_answer_contains_room_info():
    result = rooms.create_room(1, 'Anna', False, NOW)
    state = result['state']
    assert state['code'] == result['room']
    assert state['owner_name'] == 'Anna'
    assert state['permanent'] is False
    assert state['admin'] == result['id']
    assert state['banned'] == []


# ------------------------------------------------------------------ Limits

def test_limit_rooms_per_account(settings):
    settings.ROOM_MAX_PER_ACCOUNT = 2
    create(1)
    create(1)
    with pytest.raises(ValueError, match='bereits 2 Räume'):
        create(1)
    create(2)  # andere Konten sind nicht betroffen


def test_limit_rooms_total(settings):
    settings.ROOM_MAX_TOTAL = 3
    for account in (1, 2, 3):
        create(account)
    with pytest.raises(ValueError, match='alle Räume belegt'):
        create(4)


def test_limit_players_per_room(settings):
    settings.ROOM_MAX_PLAYERS = 2
    r, _ = create(1)
    join(r, 2, 'Ben')
    with pytest.raises(ValueError, match='Der Raum ist voll'):
        join(r, 3, 'Cleo')
    join(r, 2, 'Ben')  # Rejoin eines Kontos, das schon drin ist, zählt nicht neu


# ------------------------------------------------------------------ Ablauf leerer Räume

def test_empty_room_expires_after_30_minutes():
    r, _ = create(now=NOW)
    rooms.sweep(NOW + EXPIRY - 1)
    assert r['code'] in rooms.rooms
    rooms.sweep(NOW + EXPIRY)
    assert r['code'] not in rooms.rooms


def test_activity_keeps_room_alive():
    r, pid = create(now=NOW)
    for step in range(1, 181):  # eine Stunde lang alle 20 Sekunden ein Abruf
        now = NOW + step * 20
        act(r, 1, pid, 'state', now)
        rooms.sweep(now)
    assert r['code'] in rooms.rooms
    rooms.sweep(NOW + 3600 + EXPIRY)
    assert r['code'] not in rooms.rooms


def test_expired_room_frees_owner_limit(settings):
    settings.ROOM_MAX_PER_ACCOUNT = 1
    create(1, now=NOW)
    rooms.sweep(NOW + EXPIRY)
    create(1, now=NOW + EXPIRY)


# ------------------------------------------------------------------ Besitzer

def test_owner_keeps_rights_after_reconnect():
    r, anna = create(1)
    ben = join(r, 2, 'Ben')
    act(r, 2, ben, 'state', NOW + 20)
    later = NOW + engine.OFFLINE_TIMEOUT + 1
    act(r, 2, ben, 'state', later)  # Anna ist jetzt 31 s offline und fliegt raus
    assert anna not in r['players']
    assert r['admin'] is None  # die Verwaltung wandert nicht zu Ben
    with pytest.raises(ValueError, match='Nur die Raumverwaltung'):
        act(r, 2, ben, 'settings', later, kind='weather', mode='manual', weather='Nebel')

    anna_new = join(r, 1, 'Anna', later)
    assert r['admin'] == anna_new
    act(r, 1, anna_new, 'settings', later, kind='weather', mode='manual', weather='Nebel')
    assert r['weather'] == 'Nebel'


def test_snapshot_admin_is_owner_player_id():
    r, anna = create(1)
    join(r, 2, 'Ben')
    state = act(r, 2, next(p for p in r['players'] if p != anna), 'state')['state']
    assert state['admin'] == anna
    assert state['owner_name'] == 'Anna'
    assert 'banned' not in state  # Sperrliste sieht nur der Besitzer


def test_transfer_owner():
    r, anna = create(1)
    ben = join(r, 2, 'Ben')
    with pytest.raises(ValueError, match='Nur der Raumbesitzer'):
        act(r, 2, ben, 'transfer_owner', target=anna)
    state = act(r, 1, anna, 'transfer_owner', target=ben)['state']
    assert r['owner_account'] == 2
    assert state['admin'] == ben
    assert state['owner_name'] == 'Ben'
    assert r['radio'][-1]['message'] == 'Ben verwaltet jetzt den Raum.'
    with pytest.raises(ValueError, match='Nur die Raumverwaltung'):
        act(r, 1, anna, 'settings', kind='weather', mode='manual', weather='Regen')


def test_transfer_owner_respects_room_limit(settings):
    settings.ROOM_MAX_PER_ACCOUNT = 1
    r, anna = create(1)
    create(2, 'Ben')
    ben = join(r, 2, 'Ben')
    with pytest.raises(ValueError, match='Ben verwaltet bereits 1 Räume'):
        act(r, 1, anna, 'transfer_owner', target=ben)


# ------------------------------------------------------------------ Kick und Sperre

def test_kick_frees_vehicle_and_dispatcher():
    r, anna = create(1)
    ben = join(r, 2, 'Ben')
    cleo = join(r, 3, 'Cleo')
    act(r, 2, ben, 'claim', vehicle='WB-3-KdoW')
    act(r, 3, cleo, 'take_ls')
    assert r['vehicles']['WB-3-KdoW']['owner'] == ben

    act(r, 1, anna, 'kick', target=ben)
    assert ben not in r['players']
    assert r['vehicles']['WB-3-KdoW']['owner'] is None
    assert r['vehicles']['WB-3-KdoW']['unattended_since'] == NOW  # KI übernimmt wie bei Verbindungsverlust
    assert r['radio'][-1]['message'] == ('Ben wurde von der Raumverwaltung entfernt. '
                                         'Florian WB 3 KdoW ist wieder frei.')

    act(r, 1, anna, 'kick', target=cleo)
    assert r['dispatcher'] is None
    assert r['radio'][-1]['message'] == 'Cleo wurde von der Raumverwaltung entfernt. Die Leitstelle ist wieder frei.'


def test_kicked_player_gets_message_and_may_rejoin():
    r, anna = create(1)
    ben = join(r, 2, 'Ben')
    act(r, 1, anna, 'kick', target=ben)
    with pytest.raises(rooms.KickedError, match='aus dem Raum entfernt'):
        act(r, 2, ben, 'state')
    assert join(r, 2, 'Ben') != ben


def test_kick_with_ban_and_unban():
    r, anna = create(1)
    ben = join(r, 2, 'Ben')
    state = act(r, 1, anna, 'kick', target=ben, ban=True)['state']
    assert state['banned'] == [{'account': 2, 'name': 'Ben'}]
    assert r['radio'][-1]['message'] == 'Ben wurde von der Raumverwaltung entfernt und für diesen Raum gesperrt.'
    with pytest.raises(rooms.KickedError, match='gesperrt'):
        act(r, 2, ben, 'state')
    with pytest.raises(ValueError, match='Du bist für diesen Raum gesperrt'):
        join(r, 2, 'Ben')

    act(r, 1, anna, 'unban', account=2)
    assert r['banned'] == {}
    join(r, 2, 'Ben')


def test_only_owner_may_kick():
    r, anna = create(1)
    ben = join(r, 2, 'Ben')
    with pytest.raises(ValueError, match='Nur der Raumbesitzer'):
        act(r, 2, ben, 'kick', target=anna)
    with pytest.raises(ValueError, match='Das bist du selbst'):
        act(r, 1, anna, 'kick', target=anna)
    with pytest.raises(ValueError, match='Spieler nicht gefunden'):
        act(r, 1, anna, 'kick', target='gibtsnicht')


# ------------------------------------------------------------------ Rejoin

def test_rejoin_returns_same_player_id():
    r, anna = create(1)
    assert join(r, 1, 'Anna') == anna
    assert join(r, 1, 'Anna') == anna
    assert len(r['players']) == 1
    assert sum('beigetreten' in m['message'] for m in r['radio']) == 1


# ------------------------------------------------------------------ Discord-Raum

@pytest.fixture
def discord_room(monkeypatch):
    monkeypatch.setattr(discord, 'ROOM', 'WESTBUMMELN')
    monkeypatch.setattr(discord, 'ROOM_OK', True)
    return 'WESTBUMMELN'


def test_discord_room_exists_without_owner_and_never_expires(discord_room):
    rooms.ensure_discord_room(NOW)
    r = rooms.get_room(discord_room)
    assert r['permanent'] is True
    assert r['owner_account'] is None
    anna = join(r, 1, 'Anna')
    assert r['admin'] == anna  # wie bisher: erster Spieler verwaltet den Raum
    rooms.sweep(NOW + 10 * EXPIRY)
    assert discord_room in rooms.rooms


def test_discord_room_has_no_kick(discord_room):
    r = rooms.get_room(discord_room)
    anna = join(r, 1, 'Anna')
    ben = join(r, 2, 'Ben')
    with pytest.raises(ValueError, match='Nur der Raumbesitzer'):
        act(r, 1, anna, 'kick', target=ben)


def test_discord_messages_reach_discord_room(discord_room):
    rooms.from_discord('Max', 'Hallo')
    assert rooms.rooms[discord_room]['radio'][-1]['author'] == 'Max (Discord)'


def test_new_code_never_equals_discord_room(discord_room, monkeypatch):
    monkeypatch.setattr(discord, 'ROOM', 'AAAAAA')
    letters = iter('A' * 6 + 'C' * 6)
    monkeypatch.setattr(rooms.secrets, 'choice', lambda alphabet: next(letters))
    assert rooms.new_code() == 'CCCCCC'


# ------------------------------------------------------------------ über HTTP

def test_http_create_join_kick(player, game_client):
    state = player.create()
    assert state['code'] == player.room

    second = game_client()
    second.account('register', name='Zweite', email='zwei@example.com', password='Funkgeraet-42')
    second.room = player.room
    second.join()
    first_id = second.id
    second.join()
    assert second.id == first_id

    response = player.api('kick', target=second.id, ban=True)
    assert response.status_code == 200, response.json()
    response = second.api('state')
    assert response.status_code == 403
    assert response.json() == {'error': rooms.KICKED_BANNED, 'kicked': True}
    assert second.api('join').json() == {'error': rooms.BANNED}


def test_http_join_unknown_room(player):
    player.room = 'ZZZZZZ'
    response = player.api('join')
    assert response.status_code == 400
    assert response.json() == {'error': rooms.NOT_FOUND}
    assert rooms.rooms == {}


def test_http_developer_counts_all_rooms(player, django_user_model):
    make_moderator(django_user_model.objects.get(username='Florian1'))
    player.create()
    player.create()
    assert player.client.get('/developer').json() == {'rooms': 2, 'players': 2, 'rooms_total': 2}
