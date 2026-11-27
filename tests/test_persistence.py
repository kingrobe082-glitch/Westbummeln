"""Räume über einen Neustart retten (game/persistence.py)."""
import json
from collections import deque

import pytest

from game import engine, persistence, rooms

T = 1_800_000_000.0  # echte Zeitpunkte (persistence verschiebt nur Werte ab EPOCH_MIN)
DOWN = 90.0  # Ausfallzeit zwischen Speichern und Laden


@pytest.fixture(autouse=True)
def state_file(tmp_path, settings, monkeypatch):
    path = tmp_path / 'state' / 'rooms.json'
    settings.ROOM_STATE_FILE = str(path)
    monkeypatch.setattr(persistence, '_loaded', True)
    monkeypatch.setattr(persistence, '_stopped', False)
    monkeypatch.setattr(persistence, '_last_fingerprint', None)
    return path


def act(r, account, pid, action, now, name='Anna', **data):
    engine.clean_offline(r, now)
    engine.update(r, now)
    return rooms.handle(r, {'action': action, 'id': pid, **data}, account, name, False, now)


def busy_room():
    """Raum mit zwei Spielern, Leitstelle, Fahrzeug auf Anfahrt, Abschnitt, Sperre und Funk."""
    result = rooms.create_room(1, 'Anna', False, T)
    r = rooms.rooms[result['room']]
    r['ai_last'] = T  # solange Anna allein ist, keinen KI-Einsatz anlegen
    anna = result['id']
    ben = act(r, 2, None, 'join', T, 'Ben')['id']
    act(r, 3, None, 'join', T, 'Carl')
    carl = next(pid for pid, p in r['players'].items() if p['account'] == 3)
    act(r, 1, anna, 'kick', T, target=carl, ban=True)
    act(r, 1, anna, 'take_ls', T)
    act(r, 2, ben, 'claim', T, 'Ben', vehicle='LZ5-LF20Wald-1')
    act(r, 1, anna, 'incident', T, title='F2 · Wohnungsbrand', address='Marktplatz')
    inc = r['incidents'][0]['id']
    act(r, 1, anna, 'dispatch', T + 1, incident=inc, vehicle='LZ5-LF20Wald-1')
    act(r, 2, ben, 'status', T + 1, 'Ben', status=3)
    act(r, 1, anna, 'section_add', T + 2, incident=inc, section='Abschnitt Nord')
    act(r, 2, ben, 'radio', T + 3, 'Ben', message='Verstanden, fahren an.')
    return r, anna, ben


def plain(value):
    """Wie JSON es sieht: Tupel und deque als Listen."""
    if isinstance(value, dict):
        return {k: plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, deque)):
        return [plain(v) for v in value]
    return value


def without_times(value):
    if isinstance(value, dict):
        return {k: without_times(v) for k, v in value.items()
                if k not in persistence.TIME_KEYS and k != 'radio_times'}
    if isinstance(value, list):
        return [without_times(v) for v in value]
    return value


def restart(now):
    """Herunterfahren (Speichern DOWN Sekunden vor now), Speicher leeren, um now neu laden."""
    assert persistence.save(force=True, now=now - DOWN)
    rooms.rooms.clear()
    rooms.closed.clear()
    return persistence.load(now)


# ------------------------------------------------------------------ Speichern → Laden

def test_roundtrip_restores_the_same_room(state_file):
    r, anna, ben = busy_room()
    code = r['code']
    before = plain(r)
    assert restart(T + 3 + DOWN) == 1
    after = rooms.rooms[code]

    assert without_times(plain(after)) == {**without_times(before), 'rev': before['rev'] + 1,
                                           'voice_messages': []}
    assert after['banned'] == {3: 'Carl'}  # Konto-ID bleibt eine Zahl
    assert after['players'][ben]['vehicle'] == 'LZ5-LF20Wald-1'
    assert after['dispatcher'] == anna
    assert 'Abschnitt Nord' in after['incidents'][0]['sections']
    assert after['radio'][-1]['message'] == 'Verstanden, fahren an.'
    assert state_file.exists() and not state_file.with_name('rooms.json.tmp').exists()


def test_game_continues_after_restart_with_same_player_ids():
    r, anna, ben = busy_room()
    code = r['code']
    restart(T + 10 + DOWN)
    r = rooms.rooms[code]
    act(r, 2, ben, 'radio', T + 11 + DOWN, 'Ben', message='Wieder da.')
    act(r, 1, anna, 'state', T + 11 + DOWN)
    assert r['radio'][-1]['message'] == 'Wieder da.'
    assert set(r['players']) == {anna, ben}


def test_downtime_does_not_count():
    r, anna, ben = busy_room()
    code = r['code']
    v = r['vehicles']['LZ5-LF20Wald-1']
    inc = r['incidents'][0]
    old = {k: v[k] for k in ('phase_at', 'phase_until')}
    old_updated, old_ai, old_weather = inc['updated'], r['ai_last'], r['weather_at']
    saved = T + 3
    restart(saved + DOWN)
    r = rooms.rooms[code]
    v = r['vehicles']['LZ5-LF20Wald-1']
    assert v['phase_at'] == old['phase_at'] + DOWN
    assert v['phase_until'] == old['phase_until'] + DOWN
    assert r['incidents'][0]['updated'] == old_updated + DOWN
    assert r['weather_at'] == old_weather + DOWN
    assert r['ai_last'] == old_ai + DOWN
    assert r['kicked'] and all(k['at'] == T + DOWN for k in r['kicked'].values())
    # Fahrzeug steht da, wo es beim Herunterfahren war, und ist nicht am Ziel.
    assert engine.vehicle_position(v, saved + DOWN) == pytest.approx(engine.vehicle_position(
        {**v, 'phase_at': old['phase_at'], 'phase_until': old['phase_until']}, saved))
    engine.update(r, saved + DOWN + 1)
    assert v['phase'] == 'anfahrt'


def test_zero_means_never_and_is_not_shifted():
    room = {'ai_last': 0, 'weather_at': 0, 'vehicles': {'X': {'phase_at': 0, 'phase_until': T}}}
    persistence.shift_times(room, DOWN)
    assert room == {'ai_last': 0, 'weather_at': 0, 'vehicles': {'X': {'phase_at': 0, 'phase_until': T + DOWN}}}


def state_file_text():
    return persistence.state_file().read_text(encoding='utf-8')


def test_players_get_a_grace_period():
    r, anna, ben = busy_room()
    code = r['code']
    now = T + 3 + 600  # zehn Minuten Ausfall
    restart(now)
    r = rooms.rooms[code]
    engine.clean_offline(r, now + persistence.GRACE - 1)
    assert set(r['players']) == {anna, ben}
    engine.clean_offline(r, now + persistence.GRACE + 1)
    assert r['players'] == {}
    assert r['vehicles']['LZ5-LF20Wald-1']['owner'] is None


def test_ai_room_keeps_its_rhythm():
    result = rooms.create_room(1, 'Anna', False, T)
    r = rooms.rooms[result['room']]
    act(r, 1, result['id'], 'state', T)  # Solo: KI legt einen Einsatz an
    assert r['ai_last'] == T
    restart(T + DOWN)
    r = rooms.rooms[result['room']]
    assert r['ai_last'] == T + DOWN


def test_closed_codes_survive():
    rooms.closed['ABCDEF'] = T
    restart(T + DOWN)
    assert rooms.closed == {'ABCDEF': T + DOWN}


def test_radio_rate_limit_is_dropped_not_broken():
    r, anna, ben = busy_room()
    assert isinstance(r['players'][ben]['radio_times'], deque)
    restart(T + 4)
    r = rooms.rooms[r['code']]
    assert 'radio_times' not in r['players'][ben]
    act(r, 2, ben, 'radio', T + 5, 'Ben', message='Noch einer.')


# ------------------------------------------------------------------ kaputte Dateien

@pytest.mark.parametrize('content', ['{kaputt', '[]', '{"version": 999, "saved_at": 1, "rooms": {}}',
                                     '{"version": 1, "saved_at": 1, "rooms": {"AAAAAA": {"code": "B"}}}',
                                     '{"version": 1}'])
def test_broken_file_starts_empty(state_file, content, caplog):
    state_file.parent.mkdir(parents=True)
    state_file.write_text(content, encoding='utf-8')
    assert persistence.load(T) == 0
    assert rooms.rooms == {}
    assert not state_file.exists()
    assert state_file.with_name('rooms.json.broken').read_text(encoding='utf-8') == content
    assert 'unbrauchbar' in caplog.text


def test_missing_file_starts_empty(state_file):
    assert persistence.load(T) == 0
    assert rooms.rooms == {}


def test_no_save_before_load(monkeypatch, state_file):
    """Ein Worker, der vor dem Laden scheitert, darf die gesicherten Räume nicht überschreiben."""
    monkeypatch.setattr(persistence, '_loaded', False)
    busy_room()
    assert not persistence.save(force=True)
    persistence.shutdown()
    assert not state_file.exists()


def test_disabled_without_path(settings):
    settings.ROOM_STATE_FILE = ''
    busy_room()
    assert not persistence.save(force=True)
    assert persistence.load(T) == 0


def test_stale_permanent_room_is_dropped(monkeypatch):
    from integrations import discord
    monkeypatch.setattr(discord, 'ROOM', 'WESTBUMMELN')
    monkeypatch.setattr(discord, 'ROOM_OK', True)
    rooms.ensure_discord_room(T)
    rooms._add_room('ALTRAUM', None, '', T)  # früherer Discord-Raum
    restart(T + 1)
    assert set(rooms.rooms) == {'WESTBUMMELN'}


# ------------------------------------------------------------------ periodisches Speichern

def test_periodic_save_only_on_change(state_file):
    r, anna, ben = busy_room()
    assert persistence.save()
    mtime = state_file.stat().st_mtime_ns
    assert not persistence.save()  # nichts geändert
    act(r, 1, anna, 'state', T + 4)  # Abruf ohne Änderung (nur last)
    assert not persistence.save()
    act(r, 2, ben, 'radio', T + 5, 'Ben', message='Neu.')
    assert persistence.save()
    assert state_file.stat().st_mtime_ns >= mtime
    rooms.close_room(r['code'], T + 6)  # Raum weg → auch eine Änderung
    assert persistence.save()
    assert json.loads(state_file_text())['rooms'] == {}


def test_shutdown_saves_once_then_stops(state_file):
    busy_room()
    persistence.shutdown()
    assert state_file.exists()
    state_file.unlink()
    persistence.shutdown()
    assert not persistence.save(force=True)  # nach dem letzten Speichern schreibt niemand mehr
    assert not state_file.exists()


def test_everything_in_a_room_is_serializable():
    """Wer neue Felder in den Raum legt, merkt hier, wenn sie sich nicht als JSON speichern lassen."""
    busy_room()
    json.loads(persistence.dumps(T))


# ------------------------------------------------------------------ KI-Leitstelle

def ki_room(seed):
    """Raum ohne Leitstelle mit zwei GF; die KI-Leitstelle legt Einsätze an und alarmiert."""
    result = rooms.create_room(1, 'Anna', False, T)
    r = rooms.rooms[result['room']]
    r['ai_seed'] = seed
    r['ai_last'] = T  # erster KI-Einsatz erst, wenn beide GF ihr Fahrzeug haben
    anna = result['id']
    ben = act(r, 2, None, 'join', T, 'Ben')['id']
    act(r, 1, anna, 'claim', T, vehicle='LZ5-LF20Wald-1')
    act(r, 2, ben, 'claim', T, 'Ben', vehicle='LZ6-RW-1')
    for t in range(1, 120):
        for p in r['players'].values():
            p['last'] = T + t
        engine.update(r, T + t)
    return r


def ki_verlauf(r, start, seconds):
    for t in range(seconds):
        for p in r['players'].values():
            p['last'] = start + t
        engine.update(r, start + t)
    return [(i['title'], i['address']) for i in r['incidents'] if i['creator'] == 'KI-Leitstelle']


def test_room_with_ai_incidents_is_saved_and_continues_the_same_way():
    r = ki_room(seed=11)
    assert any(i['creator'] == 'KI-Leitstelle' for i in r['incidents'])
    json.loads(persistence.dumps(T + 120))  # nichts im Raum, das JSON nicht kann
    code = r['code']
    assert restart(T + 120 + DOWN) == 1
    restored = rooms.rooms[code]
    assert restored['ai_seed'] == 11
    after_restart = ki_verlauf(restored, T + 120 + DOWN, 300)
    # Derselbe Raum ohne Neustart (eigener Speicherstand) legt dieselben Einsätze an.
    rooms.rooms.clear()
    reference = ki_verlauf(ki_room(seed=11), T + 120, 300)
    assert after_restart == reference and len(reference) > 2
