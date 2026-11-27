"""Welle 2C: Spiellogik-Bugs. Zeit wird überall über `now` gesteuert."""
import pytest

from game import engine, strassen

NOW = 1_000_000.0


@pytest.fixture
def room():
    r = engine.new_room('WB')
    r['weather_mode'] = 'manual'
    return r


def join(r, account, name, now=NOW):
    return engine.handle(r, {'action': 'join'}, account, name, False, now)['id']


def act(r, pid, account, action, now=NOW, **data):
    result = engine.handle(r, {'action': action, 'id': pid, **data}, account, 'x', False, now)
    if action == 'dispatch':
        ausruecken(r, data.get('vehicle'), now)
    return result


def ausruecken(r, vehicle, now=NOW):
    """Spielerfahrzeuge geben ihren Status selbst: nach der Alarmierung Status 3 durch den GF."""
    v = r['vehicles'].get(vehicle)
    if v and v['owner'] and v['phase'] == 'wache' and v['incident']:
        p = r['players'][v['owner']]
        engine.handle(r, {'action': 'status', 'id': p['id'], 'status': 3}, p['account'], 'x', False, now)


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

def on_streets(pos):
    """Abstand zum nächsten Punkt auf dem Straßennetz."""
    return strassen._project(pos)[0]


def test_travel_time_is_fixed_at_alarm_despite_weather_change(room):
    room['weather'] = 'Nebel'
    ls, gf, inc = leitstelle_mit_gf(room)
    expected = engine.eta(room, room['vehicles']['WB-2-LF20'], inc['pos'])
    act(room, ls, 1, 'dispatch', incident=inc['id'], vehicle='WB-2-LF20')
    v = room['vehicles']['WB-2-LF20']
    until = v['phase_until']
    assert until == pytest.approx(NOW + expected)
    room['weather'] = 'Sonnig'  # schneller – darf die laufende Fahrt nicht verkürzen
    engine.update(room, NOW + (until - NOW) * .7)
    assert v['phase'] == 'anfahrt'
    engine.update(room, until)
    assert v['phase'] == 'vorort'


def test_return_trip_uses_fixed_duration(room):
    room['weather'] = 'Regen'
    ls, gf, inc = leitstelle_mit_gf(room)
    act(room, ls, 1, 'dispatch', incident=inc['id'], vehicle='WB-2-LF20')
    v = room['vehicles']['WB-2-LF20']
    arrival = v['phase_until']
    engine.update(room, arrival)
    duration = engine.plan_trip(room, v, inc['pos'], v['base'])[1][-1]
    act(room, ls, 1, 'close', now=arrival, incident=inc['id'])
    assert (v['phase'], v['phase_at'], v['phase_until']) == ('rueckfahrt', arrival, pytest.approx(arrival + duration))
    assert v['phase_from'] == inc['pos'] and v['phase_to'] == list(v['base'])
    assert v['phase_route'][0] == inc['pos'] and v['phase_route'][-1] == list(v['base'])
    room['weather'] = 'Nebel'
    engine.update(room, arrival + duration)
    assert v['phase'] == 'wache'
    assert 'phase_route' not in v


def test_return_trip_takes_as_long_as_approach(room):
    """Lars: „Ich bin viel zu schnell wieder an einer Wache.“ Früher dauerte jede Rückfahrt vom
    Einsatzort pauschal travel_time, egal wie weit. Jetzt: gleiche Strecke, gleiche Fahrzeit
    (nur ohne die Ausrückzeit der Anfahrt)."""
    ls, gf, inc = leitstelle_mit_gf(room, vehicle='WB-6-LF20')
    act(room, ls, 1, 'incident', title='F1 · Kleinbrand', address='Werkstraße 3')
    far = room['incidents'][-1]
    act(room, ls, 1, 'dispatch', incident=far['id'], vehicle='WB-6-LF20')
    v = room['vehicles']['WB-6-LF20']
    approach = v['phase_until'] - v['phase_at']
    forward = strassen.length(v['phase_route'])
    engine.update(room, v['phase_until'])
    assert v['phase'] == 'vorort'
    act(room, ls, 1, 'close', now=v['phase_until'] + 30, incident=far['id'])
    assert v['phase'] == 'rueckfahrt'
    assert strassen.length(v['phase_route']) == pytest.approx(forward)
    back = approach - engine.departure_time(v)
    assert v['phase_until'] - v['phase_at'] == pytest.approx(back)
    assert approach > 20  # quer über die Karte
    engine.update(room, v['phase_at'] + back * .9)
    assert v['phase'] == 'rueckfahrt'  # nicht vorzeitig zurück
    engine.update(room, v['phase_at'] + back)
    assert v['phase'] == 'wache'


def test_vehicle_position_follows_route(room):
    room['weather'] = 'Nebel'
    ls, gf, inc = leitstelle_mit_gf(room)
    act(room, ls, 1, 'incident', title='F1 · Kleinbrand', address='Werkstraße 3')
    far = room['incidents'][-1]
    act(room, ls, 1, 'dispatch', incident=far['id'], vehicle='WB-2-LF20')
    v = room['vehicles']['WB-2-LF20']
    route, times, span = v['phase_route'], v['phase_times'], v['phase_until'] - NOW
    assert route[0] == list(v['base']) and route[-1] == far['pos']
    assert len(route) > 5  # nicht mehr die Luftlinie
    assert len(times) == len(route) and times[-1] == pytest.approx(span)
    assert engine.vehicle_position(v, NOW + engine.departure_time(v)) == list(v['base'])  # Ausrückzeit
    for share in (.25, .5, .75, .9):
        pos = engine.vehicle_position(v, NOW + span * share)
        assert pos == pytest.approx(strassen.at_time(route, times, span * share)[0])
        assert on_streets(pos) < 1e-3, share
    assert engine.vehicle_position(v, NOW + span + 5) == pytest.approx(far['pos'])


def test_snapshot_contains_server_time(room):
    pid = join(room, 1, 'Anna')
    assert act(room, pid, 1, 'state', now=NOW + 5)['state']['server_time'] == NOW + 5


def test_snapshot_contains_route(room):
    ls, gf, inc = leitstelle_mit_gf(room)
    act(room, ls, 1, 'dispatch', incident=inc['id'], vehicle='WB-2-LF20')
    vehicles = {v['id']: v for v in engine.snapshot(room, NOW)['vehicles']}
    assert vehicles['WB-2-LF20']['phase_route'] == room['vehicles']['WB-2-LF20']['phase_route']


def test_closing_during_approach_returns_from_current_position(room):
    """Weiterer Fund: Abbruch während der Anfahrt ließ das Fahrzeug zum Einsatzort springen."""
    ls, gf, inc = leitstelle_mit_gf(room)  # Sonnig
    act(room, ls, 1, 'incident', title='F1 · Kleinbrand', address='Werkstraße 3')
    far = room['incidents'][-1]
    act(room, ls, 1, 'dispatch', incident=far['id'], vehicle='WB-2-LF20')
    v = room['vehicles']['WB-2-LF20']
    route, times, full = v['phase_route'], v['phase_times'], v['phase_until'] - NOW
    elapsed = full * .4
    abort = NOW + elapsed
    here = engine.vehicle_position(v, abort)
    act(room, ls, 1, 'close', now=abort, incident=far['id'])
    assert v['phase'] == 'rueckfahrt'
    assert v['phase_from'] == pytest.approx(here)
    assert v['phase_to'] == list(v['base'])
    # Zurück dauert so lange, wie das Fahrzeug schon gefahren ist (ohne die Ausrückzeit).
    back = elapsed - engine.departure_time(v)
    assert v['phase_until'] == pytest.approx(abort + back)
    # Zurück auf demselben Weg: die Rückroute ist der gefahrene Teil der Anfahrt, rückwärts.
    walked = strassen.at_time(route, times, elapsed)[1]
    assert v['phase_route'] == [pytest.approx(p) for p in walked[::-1]]
    for share in (.2, .5, .8):
        pos = engine.vehicle_position(v, abort + back * share)
        assert pos == pytest.approx(strassen.at_time(route, times, elapsed - back * share)[0], abs=1e-3)
    engine.update(room, v['phase_until'])
    # Zurück auf der Wache; Status 2 gibt der GF selbst.
    assert v['phase'] == 'wache' and v['incident'] is None


def test_vehicle_without_route_moves_linearly(room):
    """Fahrten aus Räumen von vor dem Straßennetz haben keine phase_route und laufen weiter gerade."""
    ls, gf, inc = leitstelle_mit_gf(room)
    act(room, ls, 1, 'dispatch', incident=inc['id'], vehicle='WB-2-LF20')
    v = room['vehicles']['WB-2-LF20']
    del v['phase_route'], v['phase_times']
    v['phase_until'] = NOW + 12
    base, target = v['base'], inc['pos']
    half = engine.vehicle_position(v, NOW + 6)
    assert half == pytest.approx([(base[0] + target[0]) / 2, (base[1] + target[1]) / 2])
    act(room, ls, 1, 'close', now=NOW + 6, incident=inc['id'])
    assert v['phase_route'] == [pytest.approx(half), list(base)]
    assert v['phase_until'] == pytest.approx(NOW + 12)  # halber Weg zurück = halbe Fahrzeit (12 s Sonnig)


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
    # Der KI-Einsatzort ist zufällig, die Fahrzeit hängt von der Strecke ab: bis zur Ankunft vorspulen.
    arrival = max(room['vehicles'][vid]['phase_until'] for vid in inc['assigned'])
    engine.update(room, arrival)
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
    act(room, gf, 2, 'status', now=NOW + 12, status=4)
    act(room, gf, 2, 'work', now=NOW + 12, incident=inc['id'])
    keep_online(room, ls, gf, now=NOW + 100)
    engine.update(room, NOW + 100)
    assert inc['closed']
    assert all(not s['vehicles'] for s in inc['sections'].values())


# ------------------------------------------------------------ Mehrere Fahrzeuge pro Einsatz

def test_leitstelle_alarmiert_mehrere_spielerfahrzeuge(room):
    ls, gf, inc = leitstelle_mit_gf(room)
    carla = join(room, 3, 'Carla')
    act(room, carla, 3, 'claim', vehicle='WB-1-HLF20')
    act(room, ls, 1, 'dispatch', incident=inc['id'], vehicle='WB-2-LF20')
    act(room, ls, 1, 'dispatch', incident=inc['id'], vehicle='WB-1-HLF20')
    assert inc['assigned'] == ['WB-2-LF20', 'WB-1-HLF20']
    assert all(room['vehicles'][vid]['phase'] == 'anfahrt' for vid in inc['assigned'])


def test_leitstelle_allein_alarmiert_mehrere_unbesetzte_fahrzeuge(room):
    ls = join(room, 1, 'Anna')
    act(room, ls, 1, 'take_ls')
    act(room, ls, 1, 'incident', title='F3 · Großbrand', address='Hauptstraße 5')
    inc = room['incidents'][-1]
    for vid in ('WB-1-HLF20', 'WB-1-LF20', 'WB-2-HLF20'):
        act(room, ls, 1, 'dispatch', incident=inc['id'], vehicle=vid)
    assert inc['assigned'] == ['WB-1-HLF20', 'WB-1-LF20', 'WB-2-HLF20']
    assert inc['sections']['Hauptabschnitt']['vehicles'] == inc['assigned']



@pytest.mark.parametrize('title, need', [
    ('F1 · Kleinbrand', 1), ('F2 · Wohnungsbrand', 2), ('B3 · Großbrand', 3), ('TH 2 · Person eingeklemmt', 2),
    ('BMA · Brandmeldeanlage', 1), ('Wasserschaden', 1),
])
def test_fahrzeugbedarf_aus_stichwort(title, need):
    assert engine.needed_vehicles({'title': title}) == need


def test_unbesetzt_bei_kleinem_einsatz_im_mehrspielerbetrieb_gesperrt(room):
    ls, gf = join(room, 1, 'Anna'), join(room, 2, 'Ben')
    act(room, ls, 1, 'take_ls')
    act(room, gf, 2, 'claim', vehicle='WB-2-LF20')
    act(room, ls, 1, 'incident', title='F1 · Kleinbrand', address='Hauptstraße 5')
    inc = room['incidents'][-1]
    with pytest.raises(ValueError, match='erst freie Spielerfahrzeuge'):
        act(room, ls, 1, 'dispatch', incident=inc['id'], vehicle='WB-1-HLF20')
    act(room, ls, 1, 'dispatch', incident=inc['id'], vehicle='WB-2-LF20')
    with pytest.raises(ValueError, match=r'Bedarf gedeckt \(1 Fahrzeug laut Stichwort\)'):
        act(room, ls, 1, 'dispatch', incident=inc['id'], vehicle='WB-1-HLF20')
    assert inc['assigned'] == ['WB-2-LF20']


def test_groesserer_einsatz_bekommt_unbesetzte_fahrzeuge_mit_ki_besatzung(room):
    ls, gf, inc = leitstelle_mit_gf(room)  # F2 · Wohnungsbrand: Bedarf 2
    snap = next(i for i in engine.snapshot(room, NOW)['incidents'] if i['id'] == inc['id'])
    assert snap['need'] == 2 and snap['ai_crew_block'] == 'erst freie Spielerfahrzeuge alarmieren'
    act(room, ls, 1, 'dispatch', incident=inc['id'], vehicle='WB-2-LF20')
    assert engine.ai_crew_block(room, inc) == ''
    act(room, ls, 1, 'dispatch', incident=inc['id'], vehicle='WB-1-HLF20')
    assert inc['assigned'] == ['WB-2-LF20', 'WB-1-HLF20']
    assert room['vehicles']['WB-1-HLF20']['owner'] is None
    with pytest.raises(ValueError, match='Bedarf gedeckt'):
        act(room, ls, 1, 'dispatch', incident=inc['id'], vehicle='WB-1-LF20')
    # Die KI-Besatzung beginnt vor Ort nach der Wartezeit selbst mit den Maßnahmen.
    engine.update(room, NOW + 20)
    keep_online(room, ls, gf, now=NOW + 20)
    engine.update(room, NOW + 20 + engine.UNATTENDED_DELAY)
    assert inc['working']


def test_zurueckfahrendes_fahrzeug_zaehlt_nicht_zum_bedarf(room):
    ls, gf, inc = leitstelle_mit_gf(room)
    carla = join(room, 3, 'Carla')
    act(room, carla, 3, 'claim', vehicle='WB-5-HLF20')
    act(room, ls, 1, 'dispatch', incident=inc['id'], vehicle='WB-2-LF20')
    act(room, ls, 1, 'dispatch', incident=inc['id'], vehicle='WB-5-HLF20')
    assert engine.ai_crew_block(room, inc).startswith('Bedarf gedeckt')
    room['vehicles']['WB-5-HLF20'].update(phase='rueckfahrt')
    assert engine.ai_crew_block(room, inc) == ''


# ------------------------------------------------------------ KI-Leitstelle bei unbesetzter Leitstelle

def zwei_gf_ohne_leitstelle(r):
    anna, ben = join(r, 1, 'Anna'), join(r, 2, 'Ben')
    act(r, anna, 1, 'claim', vehicle='WB-1-HLF20')
    act(r, ben, 2, 'claim', vehicle='WB-4-LF20')
    return anna, ben


def test_ki_leitstelle_laeuft_mit_mehreren_spielern_ohne_leitstelle(room, monkeypatch):
    monkeypatch.setattr(engine, 'AI_INCIDENT_TYPES', [('F1 · Kleinbrand', 1)])
    zwei_gf_ohne_leitstelle(room)
    assert engine.ai_dispatcher(room) and engine.snapshot(room, NOW)['ai_dispatcher']
    engine.update(room, NOW)
    inc = room['incidents'][0]
    assert inc['creator'] == 'KI-Leitstelle'
    # Nur Spielerfahrzeuge, und zwar das nächste zum Einsatzort.
    nearest = min(('WB-1-HLF20', 'WB-4-LF20'),
                  key=lambda vid: engine._distance(room['vehicles'][vid]['base'], inc['pos']))
    assert inc['assigned'] == [nearest]


def test_ki_leitstelle_verteilt_einsaetze_auf_freie_spielerfahrzeuge(room, monkeypatch):
    monkeypatch.setattr(engine, 'AI_INCIDENT_TYPES', [('F1 · Kleinbrand', 1)])
    zwei_gf_ohne_leitstelle(room)
    engine.update(room, NOW)
    engine.update(room, NOW + 45)
    first, second = room['incidents']
    assert {*first['assigned'], *second['assigned']} == {'WB-1-HLF20', 'WB-4-LF20'}


def test_ki_leitstelle_alarmiert_im_mehrspielerbetrieb_keine_unbesetzten(room):
    join(room, 1, 'Anna')
    join(room, 2, 'Ben')
    engine.update(room, NOW)
    assert room['incidents'][0]['creator'] == 'KI-Leitstelle'
    assert room['incidents'][0]['assigned'] == []


def test_ki_leitstelle_pausiert_bei_besetzter_leitstelle(room):
    ls, gf, inc = leitstelle_mit_gf(room)
    assert not engine.ai_dispatcher(room)
    engine.update(room, NOW + 100)
    assert room['incidents'] == [inc] and inc['assigned'] == []


def test_ki_leitstelle_springt_ein_wenn_leitstelle_frei_wird(room):
    ls, gf, inc = leitstelle_mit_gf(room)
    act(room, ls, 1, 'leave_ls')
    engine.update(room, NOW)
    assert inc['assigned'] == ['WB-2-LF20']


# ------------------------------------------------------------ KI-Einsatzrate

def gf_raum(n, seed=1, leitstelle=False):
    """Raum mit n GF auf eigenen Fahrzeugen (HLF der Wachen 1–6, dann LF); optional eine Leitstelle."""
    r = engine.new_room('WB', seed=seed)
    r['weather_mode'] = 'manual'
    vehicles = [f'WB-{unit}-{kind}' for kind in ('HLF20', 'LF20') for unit in range(1, 7)]
    gfs = []
    for i in range(n):
        pid = join(r, i, f'GF{i}')
        act(r, pid, i, 'claim', vehicle=vehicles[i])
        gfs.append((pid, i, vehicles[i]))
    if leitstelle:
        ls = join(r, 99, 'Leitstelle')
        act(r, ls, 99, 'take_ls')
    return r, gfs


# (Phase, alarmiert/im Einsatz) -> Status, den ein GF dann gibt
STATUS_WUNSCH = {('wache', True): 3, ('vorort', True): 4, ('rueckfahrt', True): 1,
                 ('rueckfahrt', False): 1, ('wache', False): 2}


def spielen(r, gfs, seconds, arbeiten=True):
    """Sekundenweise vorspulen. Die GF geben ihre Status selbst (3 nach Alarm, 4 vor Ort, 1 auf der
    Rückfahrt, 2 auf der Wache) und starten, wenn arbeiten, die Maßnahmen, sobald sie vor Ort sind."""
    open_max = 0
    for t in range(seconds):
        now = NOW + t
        keep_online(r, *r['players'], now=now)
        engine.update(r, now)
        for pid, account, vid in gfs:
            v = r['vehicles'][vid]
            wanted = STATUS_WUNSCH.get((v['phase'], bool(v['incident'])))
            if wanted and v['status'] != wanted and not (wanted == 2 and v['status'] == 6):
                act(r, pid, account, 'status', now=now, status=wanted)
            inc = next((i for i in r['incidents'] if i['id'] == v['incident']), None)
            if arbeiten and inc and not inc['closed'] and not inc['working'] and v['phase'] == 'vorort':
                act(r, pid, account, 'work', now=now, incident=inc['id'])
        open_max = max(open_max, sum(not i['closed'] for i in r['incidents']))
    return open_max


def ki_einsaetze(r):
    return [i for i in r['incidents'] if i['creator'] == 'KI-Leitstelle']


def test_ki_einsatzrate_steigt_mit_mehr_spielern():
    counts = {}
    for n in (1, 3, 6):
        r, gfs = gf_raum(n)
        spielen(r, gfs, 600)
        counts[n] = r['ai_seq']
    assert counts[1] < counts[3] < counts[6]


def test_ki_abstand_wird_kuerzer_je_mehr_gf_frei_sind():
    r, gfs = gf_raum(0)
    r['ai_gap'] = 40
    assert engine.ai_incident_gap(r) == 40
    r, gfs = gf_raum(3)
    r['ai_gap'] = 40
    assert engine.ai_incident_gap(r) == 10
    r['vehicles'][gfs[0][2]]['phase'] = 'anfahrt'  # unterwegs = nicht frei
    assert engine.ai_incident_gap(r) == 40 / 3


def test_ki_obergrenze_offener_einsaetze_haengt_von_spielern_ab():
    assert engine.ai_open_limit(gf_raum(0)[0]) == 2  # allein ohne Fahrzeug wie bisher: höchstens 2
    assert engine.ai_open_limit(gf_raum(1)[0]) == 2
    assert engine.ai_open_limit(gf_raum(3)[0]) == 4
    assert engine.ai_open_limit(gf_raum(12)[0]) == 8


def test_ki_obergrenze_greift_auch_wenn_niemand_arbeitet():
    # Die GF fahren hin, starten aber nie Maßnahmen: Einsätze bleiben offen, die KI legt nicht endlos nach.
    r, gfs = gf_raum(3)
    assert spielen(r, gfs, 1800, arbeiten=False) == engine.ai_open_limit(r) == 4
    assert sum(not i['assigned'] for i in r['incidents']) <= engine.AI_MAX_WAITING


def test_ki_obergrenze_ist_einstellbar(monkeypatch):
    monkeypatch.setattr(engine, 'AI_MAX_OPEN', 3)
    r, gfs = gf_raum(6)
    assert spielen(r, gfs, 600, arbeiten=False) == 3


def test_keine_ki_einsaetze_bei_menschlicher_leitstelle():
    r, gfs = gf_raum(6, leitstelle=True)
    spielen(r, gfs, 900)
    assert ki_einsaetze(r) == [] and r['ai_seq'] == 0


def test_ki_zufall_ist_mit_seed_reproduzierbar():
    def verlauf(seed):
        r, gfs = gf_raum(3, seed=seed)
        spielen(r, gfs, 600)
        return [(i['title'], i['address']) for i in ki_einsaetze(r)]
    assert verlauf(7) == verlauf(7)
    assert verlauf(7) != verlauf(8)


def test_ki_alarmiert_passende_fahrzeugzahl(monkeypatch):
    monkeypatch.setattr(engine, 'AI_INCIDENT_TYPES', [('F2 · Wohnungsbrand', 1)])
    r, gfs = gf_raum(3)
    engine.update(r, NOW)
    inc = r['incidents'][0]
    assert engine.needed_vehicles(inc) == 2 and len(inc['assigned']) == 2
    assert all(vid in {g[2] for g in gfs} for vid in inc['assigned'])


def test_ki_alarmiert_erst_jeden_einsatz_dann_nach(monkeypatch):
    monkeypatch.setattr(engine, 'AI_INCIDENT_TYPES', [('F3 · Dachstuhlbrand', 1)])
    r, gfs = gf_raum(2)
    engine.update(r, NOW)
    first = r['incidents'][0]
    assert len(first['assigned']) == 2  # nur zwei GF-Fahrzeuge da
    engine.update(r, NOW + 100)  # zweiter Einsatz: kein Fahrzeug frei, er wartet
    assert len(r['incidents']) == 2 and r['incidents'][1]['assigned'] == []


def test_ki_alarmiert_nicht_mehr_nach_ab_halber_arbeit(monkeypatch):
    monkeypatch.setattr(engine, 'AI_INCIDENT_TYPES', [('F2 · Wohnungsbrand', 1)])
    r, gfs = gf_raum(1)
    engine.update(r, NOW)
    inc = r['incidents'][0]
    inc['progress'] = engine.AI_REINFORCE_BELOW
    pid = join(r, 5, 'Neu')
    act(r, pid, 5, 'claim', vehicle='WB-6-LF20')
    engine.update(r, NOW + 1)
    assert inc['assigned'] == [gfs[0][2]]


def test_ki_einsaetze_haben_verschiedene_stichworte():
    r, gfs = gf_raum(6)
    spielen(r, gfs, 1800)
    assert len({i['title'] for i in ki_einsaetze(r)}) >= 6


def test_ki_settings_werden_an_die_spiellogik_uebergeben():
    from django.conf import settings as django_settings
    assert all(getattr(engine, name) == getattr(django_settings, name) for name in engine.AI_SETTINGS)
