"""GF-Knöpfe „Maßnahmen abschließen“ und „Zurück zur Wache“ (engine.complete / engine.return_home)."""
import json

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


def online(r, now):
    for p in r['players'].values():
        p['last'] = now


def on_site(r, ls, inc, *vehicles):
    """Fahrzeuge alarmieren und an der Einsatzstelle ankommen lassen; gibt die Ankunftszeit zurück."""
    for vid in vehicles:
        act(r, ls, 1, 'dispatch', incident=inc['id'], vehicle=vid)
    arrival = max(r['vehicles'][vid]['phase_until'] for vid in vehicles)
    online(r, arrival)
    engine.update(r, arrival)
    assert all(r['vehicles'][vid]['phase'] == 'vorort' for vid in vehicles)
    return arrival


def work_until(r, inc, percent, start):
    """Zeit vorspulen, bis der Einsatz mindestens percent % erreicht hat (Spieler bleiben online)."""
    now = start
    while inc['progress'] < percent and not inc['closed']:
        now += 1
        online(r, now)
        engine.update(r, now)
    return now


@pytest.fixture
def einsatz(room):
    """Anna Leitstelle, Ben GF auf WB-2-LF20 vor Ort, Maßnahmen laufen."""
    ls, ben = join(room, 1, 'Anna'), join(room, 2, 'Ben')
    act(room, ls, 1, 'take_ls')
    act(room, ben, 2, 'claim', vehicle='WB-2-LF20')
    act(room, ls, 1, 'incident', title='F1 · Kleinbrand', address='Hauptstraße 5')
    inc = room['incidents'][-1]
    arrival = on_site(room, ls, inc, 'WB-2-LF20')
    act(room, ben, 2, 'work', now=arrival, incident=inc['id'])
    return ls, ben, inc, arrival


def radio(r):
    return [(e['author'], e['message']) for e in r['radio']]


# ------------------------------------------------------------ Maßnahmen abschließen

def test_abschliessen_erst_ab_mindestfortschritt(room, einsatz):
    ls, ben, inc, now = einsatz
    with pytest.raises(ValueError, match=r'Noch zu früh: Abschließen ab 50 % Fortschritt \(jetzt 0 %\)'):
        act(room, ben, 2, 'complete', now=now, incident=inc['id'])
    assert not inc['closed'] and not inc['done']


def test_abschliessen_nur_nach_massnahmen_start(room):
    ls, ben = join(room, 1, 'Anna'), join(room, 2, 'Ben')
    act(room, ls, 1, 'take_ls')
    act(room, ben, 2, 'claim', vehicle='WB-2-LF20')
    act(room, ls, 1, 'incident', title='F1 · Kleinbrand', address='Hauptstraße 5')
    inc = room['incidents'][-1]
    now = on_site(room, ls, inc, 'WB-2-LF20')
    with pytest.raises(ValueError, match='Zuerst Maßnahmen starten'):
        act(room, ben, 2, 'complete', now=now, incident=inc['id'])


def test_einziger_gf_schliesst_ab_einsatz_ist_abgearbeitet(room, einsatz):
    ls, ben, inc, now = einsatz
    now = work_until(room, inc, engine.COMPLETE_MIN, now)
    act(room, ben, 2, 'complete', now=now, incident=inc['id'])
    v = room['vehicles']['WB-2-LF20']
    assert inc['closed'] and inc['done'] == ['WB-2-LF20']
    # Das Fahrzeug steht frei an der Einsatzstelle und wartet auf „Zurück zur Wache“.
    assert (v['phase'], v['status'], v['released_at']) == ('vorort', 4, now)
    assert engine.released(room, v)
    assert radio(room)[-2:] == [
        ('Florian WB 2 LF 20', 'Maßnahmen abgeschlossen, Einsatzstelle übergeben.'),
        ('Leitstelle', 'Einsatz F1 · Kleinbrand abgearbeitet – Einsatzstelle frei, Fahrzeuge melden Rückfahrt.'),
    ]
    with pytest.raises(ValueError, match='Einsatz nicht verfügbar'):
        act(room, ben, 2, 'complete', now=now, incident=inc['id'])


def test_abschliessen_mit_weiterem_gf_laeuft_einsatz_weiter(room):
    ls, ben, carla = join(room, 1, 'Anna'), join(room, 2, 'Ben'), join(room, 3, 'Carla')
    act(room, ls, 1, 'take_ls')
    act(room, ben, 2, 'claim', vehicle='WB-2-LF20')
    act(room, carla, 3, 'claim', vehicle='WB-2-HLF20')
    act(room, ls, 1, 'incident', title='F2 · Wohnungsbrand', address='Hauptstraße 5')
    inc = room['incidents'][-1]
    now = on_site(room, ls, inc, 'WB-2-LF20', 'WB-2-HLF20')
    act(room, ben, 2, 'work', now=now, incident=inc['id'])
    now = work_until(room, inc, engine.COMPLETE_MIN, now)
    act(room, ben, 2, 'complete', now=now, incident=inc['id'])
    assert not inc['closed'] and inc['done'] == ['WB-2-LF20']
    assert engine.released(room, room['vehicles']['WB-2-LF20'])
    assert not engine.released(room, room['vehicles']['WB-2-HLF20'])
    # Ben darf schon heimfahren, Carla arbeitet weiter.
    act(room, ben, 2, 'return_home', now=now, incident=inc['id'])
    assert room['vehicles']['WB-2-LF20']['phase'] == 'rueckfahrt'
    progress = inc['progress']
    online(room, now + 5)
    engine.update(room, now + 5)
    assert inc['progress'] > progress
    # Nur noch ein Fahrzeug arbeitet: langsamer als mit zweien.
    assert inc['progress'] - progress == pytest.approx(5 * (1.2 + .55), abs=.01)
    act(room, carla, 3, 'complete', now=now + 5, incident=inc['id'])
    assert inc['closed']


def test_ab_80_prozent_ist_einsatz_auch_mit_weiterem_gf_abgearbeitet(room):
    ls, ben, carla = join(room, 1, 'Anna'), join(room, 2, 'Ben'), join(room, 3, 'Carla')
    act(room, ls, 1, 'take_ls')
    act(room, ben, 2, 'claim', vehicle='WB-2-LF20')
    act(room, carla, 3, 'claim', vehicle='WB-2-HLF20')
    act(room, ls, 1, 'incident', title='F2 · Wohnungsbrand', address='Hauptstraße 5')
    inc = room['incidents'][-1]
    now = on_site(room, ls, inc, 'WB-2-LF20', 'WB-2-HLF20')
    act(room, ben, 2, 'work', now=now, incident=inc['id'])
    now = work_until(room, inc, engine.COMPLETE_ALL, now)
    act(room, ben, 2, 'complete', now=now, incident=inc['id'])
    assert inc['closed']
    # Carlas Fahrzeug ist mit dem Einsatzende ebenfalls frei und wartet auf ihre Rückmeldung.
    assert engine.released(room, room['vehicles']['WB-2-HLF20'])
    assert room['vehicles']['WB-2-HLF20']['phase'] == 'vorort'


def test_ki_fahrzeuge_zaehlen_als_fertig_und_fahren_sofort_heim(room):
    ls, ben = join(room, 1, 'Anna'), join(room, 2, 'Ben')
    act(room, ls, 1, 'take_ls')
    act(room, ben, 2, 'claim', vehicle='WB-2-LF20')
    act(room, ls, 1, 'incident', title='F2 · Wohnungsbrand', address='Hauptstraße 5')
    inc = room['incidents'][-1]
    now = on_site(room, ls, inc, 'WB-2-LF20', 'WB-1-HLF20')  # WB-1-HLF20 mit KI-Besatzung
    act(room, ben, 2, 'work', now=now, incident=inc['id'])
    now = work_until(room, inc, engine.COMPLETE_MIN, now)
    act(room, ben, 2, 'complete', now=now, incident=inc['id'])
    assert inc['closed']
    assert room['vehicles']['WB-1-HLF20']['phase'] == 'rueckfahrt'
    assert room['vehicles']['WB-2-LF20']['phase'] == 'vorort'


def test_abschliessen_nur_fuer_eigenes_fahrzeug_am_einsatz(room, einsatz):
    ls, ben, inc, now = einsatz
    now = work_until(room, inc, engine.COMPLETE_MIN, now)
    with pytest.raises(ValueError, match='Nur der GF des Fahrzeugs'):
        act(room, ls, 1, 'complete', now=now, incident=inc['id'])
    dora = join(room, 4, 'Dora', now=now)
    with pytest.raises(ValueError, match='Nur der GF des Fahrzeugs'):
        act(room, dora, 4, 'complete', now=now, incident=inc['id'])
    act(room, dora, 4, 'claim', now=now, vehicle='WB-3-LF20')
    with pytest.raises(ValueError, match='nicht an dieser Einsatzstelle'):
        act(room, dora, 4, 'complete', now=now, incident=inc['id'])
    assert not inc['closed']


def test_katalog_einsatz_wird_ueber_massnahmen_abgeschlossen(room, einsatz):
    """Einsätze mit Maßnahmenkatalog (inc['stichwort']) haben eigene Abschlussregeln."""
    ls, ben, inc, now = einsatz
    now = work_until(room, inc, engine.COMPLETE_MIN, now)
    inc['stichwort'] = 'F1'
    with pytest.raises(ValueError, match='über die Maßnahmen im Panel abschließen'):
        act(room, ben, 2, 'complete', now=now, incident=inc['id'])
    assert not inc['closed']


# ------------------------------------------------------------ Zurück zur Wache

def test_zurueck_zur_wache_nutzt_rueckfahrt_ueber_strassen(room, einsatz):
    ls, ben, inc, now = einsatz
    now = work_until(room, inc, engine.COMPLETE_MIN, now)
    act(room, ben, 2, 'complete', now=now, incident=inc['id'])
    v = room['vehicles']['WB-2-LF20']
    act(room, ben, 2, 'return_home', now=now + 3)
    assert (v['phase'], v['status']) == ('rueckfahrt', 1)
    assert 'released_at' not in v
    assert v['phase_route'][0] == inc['pos'] and v['phase_route'][-1] == list(v['base'])
    assert radio(room)[-1] == ('Florian WB 2 LF 20', 'Status 1 – Einsatzstelle verlassen, Rückfahrt zur Wache.')
    online(room, v['phase_until'])
    engine.update(room, v['phase_until'])
    assert (v['phase'], v['status'], v['incident']) == ('wache', 2, None)


def test_zurueck_zur_wache_nicht_waehrend_des_einsatzes(room, einsatz):
    ls, ben, inc, now = einsatz
    with pytest.raises(ValueError, match='erst „Maßnahmen abschließen“'):
        act(room, ben, 2, 'return_home', now=now)
    with pytest.raises(ValueError, match='erst „Maßnahmen abschließen“'):
        act(room, ben, 2, 'status', now=now, status=1)
    assert room['vehicles']['WB-2-LF20']['phase'] == 'vorort'
    with pytest.raises(ValueError, match='Nur der GF des Fahrzeugs'):
        act(room, ls, 1, 'return_home', now=now)


def test_zurueck_zur_wache_nur_an_der_einsatzstelle(room):
    ben = join(room, 2, 'Ben')
    act(room, ben, 2, 'claim', vehicle='WB-2-LF20')
    with pytest.raises(ValueError, match='nicht an einer Einsatzstelle'):
        act(room, ben, 2, 'return_home')


def test_status_1_an_der_einsatzstelle_heisst_rueckfahrt(room, einsatz):
    ls, ben, inc, now = einsatz
    act(room, ls, 1, 'close', now=now + 2, incident=inc['id'])
    v = room['vehicles']['WB-2-LF20']
    assert v['phase'] == 'vorort'
    assert radio(room)[-1] == ('Leitstelle', 'Einsatz F1 · Kleinbrand beendet – Einsatzstelle frei, '
                                             'Fahrzeuge melden Rückfahrt.')
    act(room, ben, 2, 'status', now=now + 4, status=1)
    assert (v['phase'], v['status']) == ('rueckfahrt', 1)


def test_leitstelle_beendet_waehrend_anfahrt_faehrt_sofort_heim(room):
    ls, ben = join(room, 1, 'Anna'), join(room, 2, 'Ben')
    act(room, ls, 1, 'take_ls')
    act(room, ben, 2, 'claim', vehicle='WB-2-LF20')
    act(room, ls, 1, 'incident', title='F1 · Kleinbrand', address='Hauptstraße 5')
    inc = room['incidents'][-1]
    act(room, ls, 1, 'dispatch', incident=inc['id'], vehicle='WB-2-LF20')
    act(room, ls, 1, 'close', now=NOW + 2, incident=inc['id'])
    assert room['vehicles']['WB-2-LF20']['phase'] == 'rueckfahrt'
    assert radio(room)[-1] == ('Leitstelle', 'Einsatz F1 · Kleinbrand beendet – Rückfahrt eingeleitet.')


def test_wartendes_fahrzeug_faehrt_nach_frist_selbst(room, einsatz):
    ls, ben, inc, now = einsatz
    act(room, ls, 1, 'close', now=now, incident=inc['id'])
    v = room['vehicles']['WB-2-LF20']
    online(room, now + engine.RETURN_DELAY - 1)
    engine.update(room, now + engine.RETURN_DELAY - 1)
    assert v['phase'] == 'vorort'
    online(room, now + engine.RETURN_DELAY)
    engine.update(room, now + engine.RETURN_DELAY)
    assert (v['phase'], v['status']) == ('rueckfahrt', 1)


def test_wartendes_fahrzeug_ohne_gf_faehrt_sofort(room, einsatz):
    ls, ben, inc, now = einsatz
    act(room, ls, 1, 'close', now=now, incident=inc['id'])
    # Ben verliert die Verbindung.
    room['players'][ls]['last'] = now + 40
    engine.clean_offline(room, now + 40)
    engine.update(room, now + 40)
    assert room['vehicles']['WB-2-LF20']['phase'] == 'rueckfahrt'


def test_freies_fahrzeug_zaehlt_nicht_zum_bedarf(room):
    ls, ben, carla = join(room, 1, 'Anna'), join(room, 2, 'Ben'), join(room, 3, 'Carla')
    act(room, ls, 1, 'take_ls')
    act(room, ben, 2, 'claim', vehicle='WB-2-LF20')
    act(room, carla, 3, 'claim', vehicle='WB-2-HLF20')
    act(room, ls, 1, 'incident', title='F2 · Wohnungsbrand', address='Hauptstraße 5')
    inc = room['incidents'][-1]
    now = on_site(room, ls, inc, 'WB-2-LF20', 'WB-2-HLF20')
    assert engine.ai_crew_block(room, inc).startswith('Bedarf gedeckt')
    act(room, ben, 2, 'work', now=now, incident=inc['id'])
    now = work_until(room, inc, engine.COMPLETE_MIN, now)
    act(room, ben, 2, 'complete', now=now, incident=inc['id'])
    assert not inc['closed']
    assert not engine.ai_crew_block(room, inc).startswith('Bedarf gedeckt')


def test_ki_modus_eigenes_fahrzeug_wartet_auf_gf(room):
    anna = join(room, 1, 'Anna')
    act(room, anna, 1, 'claim', vehicle='WB-2-LF20')
    engine.update(room, NOW)  # KI-Leitstelle legt einen Einsatz an und alarmiert Annas Fahrzeug
    inc = room['incidents'][0]
    v = room['vehicles']['WB-2-LF20']
    assert inc['assigned'] == ['WB-2-LF20']
    online(room, v['phase_until'])
    engine.update(room, v['phase_until'])
    act(room, anna, 1, 'work', now=v['phase_at'], incident=inc['id'])
    now = work_until(room, inc, engine.COMPLETE_MIN, v['phase_at'])
    act(room, anna, 1, 'complete', now=now, incident=inc['id'])
    assert inc['closed'] and v['phase'] == 'vorort'
    act(room, anna, 1, 'return_home', now=now)
    assert v['phase'] == 'rueckfahrt'


# ------------------------------------------------------------ Speichern und Anzeige

def test_neue_felder_sind_json_speicherbar(room, einsatz):
    ls, ben, inc, now = einsatz
    now = work_until(room, inc, engine.COMPLETE_MIN, now)
    act(room, ben, 2, 'complete', now=now, incident=inc['id'])
    data = json.loads(json.dumps({k: v for k, v in room.items() if k != 'players'}))
    assert data['vehicles']['WB-2-LF20']['released_at'] == now
    assert data['incidents'][0]['done'] == ['WB-2-LF20']
    snap = engine.snapshot(room, now)
    json.dumps(snap)
    assert (snap['complete_min'], snap['complete_all'], snap['return_delay']) == (50, 80, engine.RETURN_DELAY)


def test_alter_einsatz_ohne_done_feld(room, einsatz):
    """Einsätze aus Räumen von vor diesem Update haben kein 'done'."""
    ls, ben, inc, now = einsatz
    del inc['done']
    now = work_until(room, inc, engine.COMPLETE_MIN, now)
    act(room, ben, 2, 'complete', now=now, incident=inc['id'])
    assert inc['done'] == ['WB-2-LF20']
