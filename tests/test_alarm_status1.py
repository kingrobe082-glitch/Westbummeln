"""Lars: „Fahrzeuge können auch im Status 1 alarmiert werden. Sind dann halt vorbelastet und ggf. weniger Wasser.“"""
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


def keep_online(r, now):
    for p in r['players'].values():
        p['last'] = now


def incident(r, ls, address, title='F1 · Kleinbrand', now=NOW):
    act(r, ls, 1, 'incident', now=now, title=title, address=address)
    return r['incidents'][-1]


def vor_ort(r, vid='WB-2-LF20'):
    """Leitstelle Anna, GF Ben auf vid; vid steht vor Ort an der Hauptstraße. Liefert (ls, gf, inc, v, jetzt)."""
    ls, gf = join(r, 1, 'Anna'), join(r, 2, 'Ben')
    act(r, ls, 1, 'take_ls')
    act(r, gf, 2, 'claim', vehicle=vid)
    inc = incident(r, ls, 'Hauptstraße 5')
    act(r, ls, 1, 'dispatch', incident=inc['id'], vehicle=vid)
    v = r['vehicles'][vid]
    now = v['phase_until']
    keep_online(r, now)
    engine.update(r, now)
    assert v['phase'] == 'vorort' and v['status'] == 4
    return ls, gf, inc, v, now


def auf_rueckfahrt(r):
    """Wie vor_ort, dann Einsatz beendet: Fahrzeug in Status 1 auf halber Rückfahrt."""
    ls, gf, inc, v, now = vor_ort(r)
    act(r, ls, 1, 'close', now=now, incident=inc['id'])
    assert v['phase'] == 'rueckfahrt' and v['status'] == 1
    half = (v['phase_at'] + v['phase_until']) / 2
    keep_online(r, half)
    engine.update(r, half)
    return ls, gf, inc, v, half


# ------------------------------------------------------------------ Wer darf alarmiert werden

def test_alarm_aus_status_1_auf_rueckfahrt(room):
    ls, gf, old, v, now = auf_rueckfahrt(room)
    here = engine.vehicle_position(v, now)
    new = incident(room, ls, 'Werkstraße 3', now=now)
    act(room, ls, 1, 'dispatch', now=now, incident=new['id'], vehicle=v['id'])
    assert (v['phase'], v['status'], v['incident']) == ('anfahrt', 3, new['id'])
    # Die neue Anfahrt beginnt dort, wo das Fahrzeug gerade ist – nicht an der Wache.
    assert v['phase_route'][0] == pytest.approx(here, abs=1e-3)
    assert v['phase_route'][0] != pytest.approx(list(v['base']), abs=1e-2)
    assert v['phase_route'][-1] == new['pos']
    # Keine Ausrückzeit: das Fahrzeug fährt schon.
    assert v['phase_until'] == pytest.approx(now + engine.plan_trip(room, v, here, new['pos'])[1][-1], abs=.05)
    assert v['vorbelastet'] is True
    assert room['radio'][-1]['message'].endswith('Aus Status 1 alarmiert, vorbelastet.')
    # Der alte Einsatz bleibt abgeschlossen und behält seine Fahrzeugliste.
    assert old['closed'] and v['id'] in old['assigned']
    assert new['sections']['Hauptabschnitt']['vehicles'] == [v['id']]


def test_alarm_aus_status_1_vor_ort_verlaesst_alten_einsatz(room):
    ls, gf, old, v, now = vor_ort(room)
    act(room, ls, 1, 'section_add', now=now, incident=old['id'], section='Nord')
    act(room, ls, 1, 'section_assign', now=now, incident=old['id'], section='Nord', vehicle=v['id'])
    act(room, gf, 2, 'status', now=now, status=1)  # GF meldet sich über Funk frei
    new = incident(room, ls, 'Werkstraße 3', now=now)
    act(room, ls, 1, 'dispatch', now=now, incident=new['id'], vehicle=v['id'])
    assert (v['phase'], v['status'], v['incident']) == ('anfahrt', 3, new['id'])
    assert v['phase_route'][0] == pytest.approx(old['pos'], abs=1e-3)
    # Der alte, noch offene Einsatz führt das Fahrzeug nicht mehr – weder zugeordnet noch im Abschnitt.
    assert not old['closed']
    assert v['id'] not in old['assigned']
    assert all(v['id'] not in s['vehicles'] for s in old['sections'].values())
    assert v['id'] in new['assigned']


def test_freigegebenes_fahrzeug_an_der_einsatzstelle(room):
    """GF-Knöpfe: Nach „Maßnahmen abschließen“ wartet das Fahrzeug in Status 4 mit released_at vor Ort."""
    ls, gf, old, v, now = vor_ort(room)
    old.setdefault('done', []).append(v['id'])
    v['released_at'] = now
    assert v['status'] == 4 and engine.alarmable(v)
    new = incident(room, ls, 'Werkstraße 3', now=now)
    act(room, ls, 1, 'dispatch', now=now, incident=new['id'], vehicle=v['id'])
    assert (v['phase'], v['status'], v['vorbelastet']) == ('anfahrt', 3, True)
    assert v['id'] not in old['assigned'] and v['id'] not in old['done']
    assert room['radio'][-1]['message'].endswith('Frei an der Einsatzstelle alarmiert, vorbelastet.')


def test_alarm_in_status_3_4_6_verboten(room):
    ls, gf, inc, v, now = vor_ort(room)
    other = incident(room, ls, 'Werkstraße 3', now=now)
    with pytest.raises(ValueError, match='nicht frei'):  # Status 4
        act(room, ls, 1, 'dispatch', now=now, incident=other['id'], vehicle=v['id'])
    act(room, ls, 1, 'dispatch', now=now, incident=other['id'], vehicle='WB-2-HLF20')
    with pytest.raises(ValueError, match='nicht frei'):  # Status 3
        act(room, ls, 1, 'dispatch', now=now, incident=inc['id'], vehicle='WB-2-HLF20')
    room['vehicles']['WB-3-LF20']['status'] = 6
    with pytest.raises(ValueError, match='nicht frei'):  # Status 6 auf der Wache
        act(room, ls, 1, 'dispatch', now=now, incident=inc['id'], vehicle='WB-3-LF20')


def test_status_1_waehrend_anfahrt_bleibt_gesperrt(room):
    ls, gf = join(room, 1, 'Anna'), join(room, 2, 'Ben')
    act(room, ls, 1, 'take_ls')
    act(room, gf, 2, 'claim', vehicle='WB-2-LF20')
    inc = incident(room, ls, 'Hauptstraße 5')
    act(room, ls, 1, 'dispatch', incident=inc['id'], vehicle='WB-2-LF20')
    act(room, gf, 2, 'status', status=1)
    assert not engine.alarmable(room['vehicles']['WB-2-LF20'])


# ------------------------------------------------------------------ Vorbelastung

def test_vorbelastung_bleibt_bis_zur_wache(room):
    ls, gf, old, v, now = auf_rueckfahrt(room)
    v['tank'] = 40  # Füllstand, falls die Maßnahmen ihn schon führen
    new = incident(room, ls, 'Werkstraße 3', now=now)
    act(room, ls, 1, 'dispatch', now=now, incident=new['id'], vehicle=v['id'])
    assert v['tank'] == 40 and v['vorbelastet']
    keep_online(room, v['phase_until'])
    engine.update(room, v['phase_until'])
    assert v['phase'] == 'vorort' and v['tank'] == 40 and v['vorbelastet']
    act(room, ls, 1, 'close', now=v['phase_until'], incident=new['id'])
    keep_online(room, v['phase_until'])
    engine.update(room, v['phase_until'])
    assert v['phase'] == 'wache' and v['vorbelastet'] is False


def test_alarm_von_der_wache_ist_nicht_vorbelastet(room):
    ls, gf, inc, v, now = vor_ort(room)
    assert v['vorbelastet'] is False
    assert not room['radio'][-2]['message'].endswith('vorbelastet.')


# ------------------------------------------------------------------ Anzeige

def test_snapshot_liefert_fahrzeit_fuer_alarmierbare(room):
    ls, gf, old, v, now = auf_rueckfahrt(room)
    new = incident(room, ls, 'Werkstraße 3', now=now)
    eta = next(i for i in engine.snapshot(room, now)['incidents'] if i['id'] == new['id'])['eta']
    assert v['id'] in eta and 'WB-6-LF20' in eta
    assert eta[v['id']] == round(engine.alarm_eta(room, v, new['pos'], now))
    room['vehicles']['WB-6-LF20']['status'] = 6
    v['status'] = 3
    eta = next(i for i in engine.snapshot(room, now)['incidents'] if i['id'] == new['id'])['eta']
    assert 'WB-6-LF20' not in eta and v['id'] not in eta  # Status 6 und Status 3


def test_status_1_spielerfahrzeug_geht_vor_ki_besatzung(room):
    ls, gf, old, v, now = auf_rueckfahrt(room)
    new = incident(room, ls, 'Werkstraße 3', now=now)
    assert engine.ai_crew_block(room, new) == 'erst freie Spielerfahrzeuge alarmieren'


# ------------------------------------------------------------------ KI-Leitstelle

def ki_mit_zwei_gf(r):
    """Zwei GF ohne Leitstelle auf den beiden Fahrzeugen derselben Wache; KI legt selbst keine Einsätze an."""
    anna, ben = join(r, 1, 'Anna'), join(r, 2, 'Ben')
    act(r, anna, 1, 'claim', vehicle='WB-2-LF20')
    act(r, ben, 2, 'claim', vehicle='WB-2-HLF20')
    r['ai_last'] = NOW + 10_000
    return anna, ben


def test_ki_bevorzugt_bei_gleicher_fahrzeit_die_wache(room, monkeypatch):
    ki_mit_zwei_gf(room)
    s1 = room['vehicles']['WB-2-LF20']
    engine._start_trip(s1, 'rueckfahrt', [[.6, .6], list(s1['base'])], [0, 60], NOW - 30)
    s1['status'] = 1
    inc = engine.new_incident('F1 · Kleinbrand', 'Kirchstraße', [.56, .58], 'KI-Leitstelle', NOW)
    room['incidents'].append(inc)
    # Gleiche Fahrzeit (auf volle Sekunden): die Wache gewinnt, obwohl das S1-Fahrzeug zuerst steht.
    monkeypatch.setattr(engine, 'alarm_eta', lambda r, v, pos, now: 30.2 if v is s1 else 29.8)
    engine.run_ai(room, NOW)
    assert inc['assigned'] == ['WB-2-HLF20']


def test_ki_nimmt_status_1_wenn_es_schneller_ist(room):
    ki_mit_zwei_gf(room)
    s1 = room['vehicles']['WB-2-LF20']
    inc = engine.new_incident('F1 · Kleinbrand', 'Kirchstraße', [.56, .58], 'KI-Leitstelle', NOW)
    # Auf der Rückfahrt vom Einsatzort nebenan: viel schneller dort als das Fahrzeug auf der Wache.
    engine._start_trip(s1, 'rueckfahrt', [[.58, .58], list(s1['base'])], [0, 60], NOW - 1)
    s1['status'] = 1
    room['incidents'].append(inc)
    on_station = room['vehicles']['WB-2-HLF20']
    assert engine.alarm_eta(room, s1, inc['pos'], NOW) < engine.alarm_eta(room, on_station, inc['pos'], NOW)
    engine.run_ai(room, NOW)
    assert inc['assigned'] == ['WB-2-LF20'] and s1['vorbelastet']


def test_ki_alarmiert_status_1_wenn_nichts_auf_der_wache(room):
    ki_mit_zwei_gf(room)
    for vid in ('WB-2-LF20', 'WB-2-HLF20'):
        v = room['vehicles'][vid]
        engine._start_trip(v, 'rueckfahrt', [[.8, .8], list(v['base'])], [0, 60], NOW - 30)
        v['status'] = 1
    room['vehicles']['WB-2-HLF20']['status'] = 3  # nicht alarmierbar
    inc = engine.new_incident('F1 · Kleinbrand', 'Kirchstraße', [.56, .58], 'KI-Leitstelle', NOW)
    room['incidents'].append(inc)
    engine.run_ai(room, NOW)
    v = room['vehicles']['WB-2-LF20']
    assert inc['assigned'] == ['WB-2-LF20'] and v['phase'] == 'anfahrt' and v['vorbelastet']
    assert room['radio'][-1]['author'] == 'KI-Leitstelle'
    assert room['radio'][-1]['message'].endswith('Aus Status 1 alarmiert, vorbelastet.')


def test_ki_allein_nimmt_erst_fahrzeuge_von_der_wache(room):
    join(room, 1, 'Anna')  # allein: unbesetzte Fahrzeuge mit KI-Besatzung
    room['ai_last'] = NOW + 10_000
    first = room['vehicles']['WB-1-HLF20']
    engine._start_trip(first, 'rueckfahrt', [[.3, .5], list(first['base'])], [0, 60], NOW - 30)
    first['status'] = 1
    inc = engine.new_incident('F1 · Kleinbrand', 'Kirchstraße', [.56, .58], 'KI-Leitstelle', NOW)
    room['incidents'].append(inc)
    engine.run_ai(room, NOW)
    assert inc['assigned'] and inc['assigned'][0] != 'WB-1-HLF20'
    assert room['vehicles'][inc['assigned'][0]]['vorbelastet'] is False
