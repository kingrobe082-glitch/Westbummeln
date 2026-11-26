"""Welle 2C: Spiellogik-Bugs. Zeit wird überall über `now` gesteuert."""
import pytest

from game import engine

NOW = 1_000_000.0


@pytest.fixture
def room():
    r = engine.new_room('WB')
    r['weather_mode'] = 'manual'
    return r


def join(r, account, name, now=NOW):
    return engine.handle(r, {'action': 'join'}, account, name, False, now)['id']


def act(r, pid, account, action, now=NOW, **data):
    return engine.handle(r, {'action': action, 'id': pid, **data}, account, 'x', False, now)


def leitstelle_mit_gf(r, vehicle='WB-2-LF20'):
    """Zwei Spieler: Anna besetzt die Leitstelle, Ben das Fahrzeug; ein Einsatz an der Hauptstraße."""
    ls = join(r, 1, 'Anna')
    gf = join(r, 2, 'Ben')
    act(r, ls, 1, 'take_ls')
    act(r, gf, 2, 'claim', vehicle=vehicle)
    act(r, ls, 1, 'incident', title='F2 · Wohnungsbrand', address='Hauptstraße 5')
    return ls, gf, r['incidents'][-1]


def keep_online(r, *pids, now):
    for pid in pids:
        r['players'][pid]['last'] = now


# ------------------------------------------------------------ Bug 1: Fahrzeit fest beim Alarm

def test_travel_time_is_fixed_at_alarm_despite_weather_change(room):
    room['weather'] = 'Nebel'  # 20 s
    ls, gf, inc = leitstelle_mit_gf(room)
    act(room, ls, 1, 'dispatch', incident=inc['id'], vehicle='WB-2-LF20')
    v = room['vehicles']['WB-2-LF20']
    assert v['phase_until'] == NOW + 20
    room['weather'] = 'Sonnig'  # 12 s – darf die laufende Fahrt nicht verkürzen
    engine.update(room, NOW + 12)
    assert v['phase'] == 'anfahrt'
    engine.update(room, NOW + 20)
    assert v['phase'] == 'vorort'


def test_return_trip_uses_fixed_duration(room):
    room['weather'] = 'Regen'  # 17 s
    ls, gf, inc = leitstelle_mit_gf(room)
    act(room, ls, 1, 'dispatch', incident=inc['id'], vehicle='WB-2-LF20')
    engine.update(room, NOW + 17)
    act(room, ls, 1, 'close', now=NOW + 17, incident=inc['id'])
    v = room['vehicles']['WB-2-LF20']
    assert (v['phase'], v['phase_at'], v['phase_until']) == ('rueckfahrt', NOW + 17, NOW + 34)
    assert v['phase_from'] == inc['pos'] and v['phase_to'] == list(v['base'])
    room['weather'] = 'Nebel'
    engine.update(room, NOW + 34)
    assert v['phase'] == 'wache'


def test_vehicle_position_interpolates_between_phase_at_and_until(room):
    room['weather'] = 'Nebel'
    ls, gf, inc = leitstelle_mit_gf(room)
    act(room, ls, 1, 'dispatch', incident=inc['id'], vehicle='WB-2-LF20')
    v = room['vehicles']['WB-2-LF20']
    base, target = v['base'], inc['pos']
    half = engine.vehicle_position(v, NOW + 10)
    assert half == pytest.approx([(base[0] + target[0]) / 2, (base[1] + target[1]) / 2])
    assert engine.vehicle_position(v, NOW + 25) == pytest.approx(target)


def test_snapshot_contains_server_time(room):
    pid = join(room, 1, 'Anna')
    assert act(room, pid, 1, 'state', now=NOW + 5)['state']['server_time'] == NOW + 5


def test_closing_during_approach_returns_from_current_position(room):
    """Weiterer Fund: Abbruch während der Anfahrt ließ das Fahrzeug zum Einsatzort springen."""
    ls, gf, inc = leitstelle_mit_gf(room)  # Sonnig: 12 s
    act(room, ls, 1, 'dispatch', incident=inc['id'], vehicle='WB-2-LF20')
    v = room['vehicles']['WB-2-LF20']
    halfway = engine.vehicle_position(v, NOW + 6)
    act(room, ls, 1, 'close', now=NOW + 6, incident=inc['id'])
    assert v['phase'] == 'rueckfahrt'
    assert v['phase_from'] == pytest.approx(halfway)
    assert v['phase_until'] == pytest.approx(NOW + 12)  # halber Weg zurück = halbe Fahrzeit


# ------------------------------------------------------------ Bug 2: offene Einsätze bleiben sichtbar

def close_many(r, ls, count, now=NOW):
    for n in range(count):
        act(r, ls, 1, 'incident', now=now, title=f'F1 · Nr. {n}', address='Marktplatz')
        act(r, ls, 1, 'close', now=now, incident=r['incidents'][-1]['id'])


def test_old_open_incident_stays_in_snapshot(room):
    ls, gf, old = leitstelle_mit_gf(room)
    close_many(room, ls, 45)
    incidents = engine.snapshot(room, NOW)['incidents']
    assert old['id'] in [i['id'] for i in incidents]
    assert sum(i['closed'] for i in incidents) == engine.SNAPSHOT_CLOSED


def test_closed_incidents_are_limited_in_memory(room):
    ls, gf, old = leitstelle_mit_gf(room)
    close_many(room, ls, engine.KEEP_CLOSED + 10)
    closed = [i for i in room['incidents'] if i['closed']]
    assert len(closed) == engine.KEEP_CLOSED
    assert closed[-1]['title'] == f'F1 · Nr. {engine.KEEP_CLOSED + 9}'
    assert old in room['incidents']


# ------------------------------------------------------------ Bug 3: doppeltes Beenden

def test_closing_twice_is_refused(room):
    ls, gf, inc = leitstelle_mit_gf(room)
    act(room, ls, 1, 'dispatch', incident=inc['id'], vehicle='WB-2-LF20')
    act(room, ls, 1, 'close', now=NOW + 5, incident=inc['id'])
    v = room['vehicles']['WB-2-LF20']
    radio = len(room['radio'])
    with pytest.raises(ValueError, match='bereits abgeschlossen'):
        act(room, ls, 1, 'close', now=NOW + 8, incident=inc['id'])
    assert v['phase_at'] == NOW + 5
    assert len(room['radio']) == radio


# ------------------------------------------------------------ Bug 4: kein doppelter Abschnittseintrag

def test_realarm_does_not_duplicate_main_section(room):
    ls, gf, inc = leitstelle_mit_gf(room)
    act(room, ls, 1, 'dispatch', incident=inc['id'], vehicle='WB-2-LF20')
    act(room, ls, 1, 'section_add', incident=inc['id'], section='Brandbekämpfung')
    act(room, ls, 1, 'section_assign', incident=inc['id'], vehicle='WB-2-LF20', section='Brandbekämpfung')
    v = room['vehicles']['WB-2-LF20']
    # Fahrzeug wird z. B. nach einer Rückfahrt erneut zum selben (noch offenen) Einsatz alarmiert.
    v.update(phase='wache', status=2, incident=None)
    act(room, ls, 1, 'dispatch', incident=inc['id'], vehicle='WB-2-LF20')
    entries = [name for name, s in inc['sections'].items() for vid in s['vehicles'] if vid == 'WB-2-LF20']
    assert entries == ['Brandbekämpfung']


def test_ai_dispatch_does_not_duplicate_main_section(room):
    inc = engine.new_incident('F1', 'Marktplatz', [.41, .65], 'KI-Leitstelle', NOW)
    room['incidents'].append(inc)
    v = room['vehicles']['WB-1-HLF20']
    engine.ai_dispatch(room, inc, v, NOW)
    v.update(phase='wache', status=2, incident=None)
    engine.ai_dispatch(room, inc, v, NOW + 1)
    assert inc['sections']['Hauptabschnitt']['vehicles'] == ['WB-1-HLF20']


# ------------------------------------------------------------ Bug 5: verwaiste Fahrzeuge vor Ort

def test_unattended_vehicle_starts_work_in_multiplayer(room):
    ls, gf, inc = leitstelle_mit_gf(room)
    act(room, ls, 1, 'dispatch', incident=inc['id'], vehicle='WB-2-LF20')
    engine.update(room, NOW + 12)
    assert room['vehicles']['WB-2-LF20']['phase'] == 'vorort'
    # Ben verliert die Verbindung, Anna bleibt online; ein dritter Spieler hält den Mehrspielermodus.
    third = join(room, 3, 'Carla', now=NOW + 12)
    keep_online(room, ls, third, now=NOW + 40)
    engine.clean_offline(room, NOW + 43)
    assert gf not in room['players'] and not engine.ai_mode(room)
    assert room['vehicles']['WB-2-LF20']['owner'] is None
    engine.update(room, NOW + 43 + engine.UNATTENDED_DELAY - 1)
    assert not inc['working']
    engine.update(room, NOW + 43 + engine.UNATTENDED_DELAY)
    assert inc['working']
    assert room['radio'][-1]['message'].startswith('KI übernimmt Florian WB 2 LF 20')


def test_unattended_vehicle_finishes_incident(room):
    ls, gf, inc = leitstelle_mit_gf(room)
    act(room, ls, 1, 'dispatch', incident=inc['id'], vehicle='WB-2-LF20')
    engine.update(room, NOW + 12)
    room['vehicles']['WB-2-LF20']['owner'] = None
    room['vehicles']['WB-2-LF20']['unattended_since'] = NOW + 12
    engine.update(room, NOW + 32)
    engine.update(room, NOW + 200)
    assert inc['closed']


def test_owned_vehicle_on_site_waits_for_its_player(room):
    ls, gf, inc = leitstelle_mit_gf(room)
    act(room, ls, 1, 'dispatch', incident=inc['id'], vehicle='WB-2-LF20')
    engine.update(room, NOW + 12)
    engine.update(room, NOW + 100)
    assert not inc['working']


def test_ai_mode_still_starts_work_immediately(room):
    join(room, 1, 'Anna')
    engine.update(room, NOW)
    inc = room['incidents'][0]
    engine.update(room, NOW + 12)
    assert inc['working']


# ------------------------------------------------------------ Bug 6: Abschnitte abgeschlossener Einsätze

def test_closed_incident_releases_section_vehicles(room):
    ls, gf, inc = leitstelle_mit_gf(room)
    act(room, ls, 1, 'dispatch', incident=inc['id'], vehicle='WB-2-LF20')
    act(room, ls, 1, 'close', incident=inc['id'])
    assert all(not s['vehicles'] for s in inc['sections'].values())
    shown = next(i for i in engine.snapshot(room, NOW)['incidents'] if i['id'] == inc['id'])
    assert 'sections' not in shown


def test_auto_finished_incident_releases_section_vehicles(room):
    ls, gf, inc = leitstelle_mit_gf(room)
    act(room, ls, 1, 'dispatch', incident=inc['id'], vehicle='WB-2-LF20')
    engine.update(room, NOW + 12)
    act(room, gf, 2, 'work', now=NOW + 12, incident=inc['id'])
    keep_online(room, ls, gf, now=NOW + 100)
    engine.update(room, NOW + 100)
    assert inc['closed']
    assert all(not s['vehicles'] for s in inc['sections'].values())
