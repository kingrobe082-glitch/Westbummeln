"""Gerätehäuser GH1–GH5 mit je einem Fahrzeug (LF 10): Flotte, Straßenanbindung, Disposition."""
import pytest

from game import engine, strassen

NOW = 1_000_000.0
GH_IDS = ['WB-GH1-LF10', 'WB-GH2-LF10', 'WB-GH3-LF10', 'WB-GH4-LF10', 'WB-GH5-LF10']
WIESENSTRASSE = next([x, y] for name, x, y in engine.PLACES if name == 'Wiesenstraße')


@pytest.fixture
def room():
    r = engine.new_room('WB', seed=1)
    r['weather_mode'] = 'manual'
    return r


def join(r, account, name, now=NOW):
    return engine.handle(r, {'action': 'join'}, account, name, False, now)['id']


def act(r, pid, account, action, now=NOW, **data):
    return engine.handle(r, {'action': action, 'id': pid, **data}, account, 'x', False, now)


def ki_einsatz(r, title, pos=WIESENSTRASSE, address='Wiesenstraße'):
    """Einsatz für die KI-Leitstelle anlegen und einmal disponieren lassen (ohne neuen Zufallseinsatz)."""
    r['ai_last'] = NOW
    r['ai_gap'] = 10_000
    inc = engine.new_incident(title, address, list(pos), 'Test', NOW)
    r['incidents'].append(inc)
    engine.run_ai(r, NOW)
    return inc


# ------------------------------------------------------------ Flotte

def test_jedes_geraetehaus_hat_ein_lf10(room):
    gh = [v for v in room['vehicles'].values() if str(v['unit']).startswith('GH')]
    assert [v['id'] for v in gh] == GH_IDS
    v = room['vehicles']['WB-GH4-LF10']
    assert v['call'] == 'Florian WB GH4 LF 10'
    assert (v['kind'], v['seats'], v['unit']) == ('LF 10', 9, 'GH4')
    assert tuple(v['base']) == engine.GERAETEHAEUSER['GH4'][1]
    assert all(x['phase'] == 'wache' and x['status'] == 2 for x in gh)


def test_lf10_loescht_hat_aber_keinen_rettungssatz(room):
    lf10 = engine.vehicle_type(room['vehicles']['WB-GH1-LF10'])
    assert {'loeschen', 'pumpe', 'wasserversorgung'} <= set(lf10['abilities'])
    assert 'rettungssatz' not in lf10['abilities']
    assert 1000 <= lf10['tank'] <= 1200
    assert 'rettungssatz' in engine.vehicle_type(room['vehicles']['WB-1-HLF20'])['abilities']


def test_gerätehaus_typ_ist_nur_eine_datenzeile():
    """Wechsel auf TSF-W: GH_KIND ändern reicht, Sitzplätze kommen aus VEHICLE_TYPES."""
    v = engine._fleet_vehicle('GH2', 'TSF-W', engine.GERAETEHAEUSER['GH2'][1])
    assert (v['id'], v['call'], v['seats']) == ('WB-GH2-TSFW', 'Florian WB GH2 TSF-W', 6)


def test_geraetehaeuser_sind_keine_einsatzorte():
    for _, pos in engine.GERAETEHAEUSER.values():
        assert not engine.safe_location(pos)
    assert engine.safe_location(WIESENSTRASSE)


# ------------------------------------------------------------ Straßennetz

@pytest.mark.parametrize('gh, street', [
    ('GH1', 'Waldstraße'), ('GH2', 'Ahornallee'), ('GH3', 'Tannenfeld'), ('GH4', 'Mühlenweg'),
    ('GH5', 'Werkstraße'),
])
def test_geraetehaus_faehrt_ueber_seine_strasse_aus(gh, street):
    """Wie bei den Wachen: kurze Zufahrt vom Gerätehaus zur nächsten Straße (Hofeinfahrt)."""
    base = engine.GERAETEHAEUSER[gh][1]
    _, (a, b), _ = strassen._project(base)
    on = {name for name, points in strassen.STREETS for p in points
          if tuple(strassen._point(p)) in (strassen.NODES[a], strassen.NODES[b])}
    assert street in on


def test_gh4_hat_den_kuerzesten_weg_zur_wiesenstrasse(room):
    weg = {v['id']: engine.drive_distance(v, WIESENSTRASSE) for v in room['vehicles'].values()}
    assert min(weg, key=weg.get) == 'WB-GH4-LF10'


# ------------------------------------------------------------ KI-Leitstelle

def test_ki_alarmiert_gh4_zur_wiesenstrasse(room):
    join(room, 1, 'Anna')  # allein im Raum: KI-Leitstelle mit KI-Besatzungen
    inc = ki_einsatz(room, 'F1 · Kleinbrand')
    assert inc['assigned'] == ['WB-GH4-LF10']
    v = room['vehicles']['WB-GH4-LF10']
    assert v['phase'] == 'anfahrt' and v['status'] == 3
    assert v['phase_route'][0] == list(engine.GERAETEHAEUSER['GH4'][1])


def test_bei_groesserem_einsatz_kommt_der_loeschzug_dazu(room):
    join(room, 1, 'Anna')
    inc = ki_einsatz(room, 'F2 · Wohnungsbrand')
    assert inc['assigned'][0] == 'WB-GH4-LF10'
    assert len(inc['assigned']) == 2
    assert isinstance(room['vehicles'][inc['assigned'][1]]['unit'], int)  # ein Fahrzeug eines Löschzugs


def test_th2_braucht_den_rettungssatz_des_hlf(room):
    join(room, 1, 'Anna')
    inc = ki_einsatz(room, 'TH2 · Verkehrsunfall, eingeklemmte Person')
    assert room['vehicles'][inc['assigned'][0]]['kind'] == 'HLF 20'


def test_ki_waehlt_unter_spielerfahrzeugen_das_naechste_gh(room):
    anna, ben = join(room, 1, 'Anna'), join(room, 2, 'Ben')
    act(room, anna, 1, 'claim', vehicle='WB-1-HLF20')
    act(room, ben, 2, 'claim', vehicle='WB-GH4-LF10')
    inc = ki_einsatz(room, 'F1 · Kleinbrand')
    assert inc['assigned'] == ['WB-GH4-LF10']


# ------------------------------------------------------------ Spieler

def test_gf_uebernimmt_gh_fahrzeug_und_leitstelle_alarmiert_es(room):
    ls, gf = join(room, 1, 'Anna'), join(room, 2, 'Ben')
    act(room, ls, 1, 'take_ls')
    act(room, gf, 2, 'claim', vehicle='WB-GH4-LF10')
    assert room['vehicles']['WB-GH4-LF10']['owner'] == gf
    assert room['players'][gf]['role'] == 'gf'
    act(room, ls, 1, 'incident', title='F1 · Kleinbrand', address='Wiesenstraße 3')
    inc = room['incidents'][-1]
    state = act(room, ls, 1, 'dispatch', incident=inc['id'], vehicle='WB-GH4-LF10')['state']
    v = next(x for x in state['vehicles'] if x['id'] == 'WB-GH4-LF10')
    assert v['phase'] == 'anfahrt' and v['incident'] == inc['id']
    assert room['radio'][-1]['message'] == 'Alarm Florian WB GH4 LF 10: F1 · Kleinbrand, Wiesenstraße 3.'


def test_gh_fahrzeug_kommt_nach_dem_einsatz_zurueck(room):
    join(room, 1, 'Anna')
    inc = ki_einsatz(room, 'F1 · Kleinbrand')
    v = room['vehicles']['WB-GH4-LF10']
    engine.update(room, v['phase_until'])
    assert v['phase'] == 'vorort'
    engine._finish_incident(room, inc, v['phase_at'] + 1)
    assert v['phase'] == 'rueckfahrt' and v['phase_route'][-1] == list(engine.GERAETEHAEUSER['GH4'][1])
    room['ai_last'] = v['phase_until']
    engine.update(room, v['phase_until'])
    assert v['phase'] == 'wache' and v['status'] == 2


# ------------------------------------------------------------ alte Räume

def test_alter_raum_ohne_gh_fahrzeuge_wird_ergaenzt(room):
    for vid in GH_IDS:
        del room['vehicles'][vid]
    room['vehicles']['WB-1-HLF20']['status'] = 6
    assert engine.complete_fleet(room) == 5
    assert len(room['vehicles']) == 23
    assert room['vehicles']['WB-1-HLF20']['status'] == 6  # Vorhandenes bleibt, wie es war
    assert room['vehicles']['WB-GH4-LF10']['phase'] == 'wache'
    assert engine.complete_fleet(room) == 0
