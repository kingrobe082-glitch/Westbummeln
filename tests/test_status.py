"""FMS-Status: Spieler geben ihren Status selbst, die Leitstelle beantwortet Status 5 (Sprechwunsch)."""
import pytest

from game import engine

NOW = 1_000_000.0


@pytest.fixture
def room():
    r = engine.new_room('WB')
    r['weather_mode'] = 'manual'
    return r


def join(r, account, name):
    return engine.handle(r, {'action': 'join'}, account, name, False, NOW)['id']


def act(r, pid, account, action, now=NOW, **data):
    return engine.handle(r, {'action': action, 'id': pid, **data}, account, 'x', False, now)


@pytest.fixture
def lage(room):
    """Anna in der Leitstelle, Ben auf WB-2-LF20, ein Einsatz, das Fahrzeug ist alarmiert."""
    ls, gf = join(room, 1, 'Anna'), join(room, 2, 'Ben')
    act(room, ls, 1, 'take_ls')
    act(room, gf, 2, 'claim', vehicle='WB-2-LF20')
    act(room, ls, 1, 'incident', title='F2 · Wohnungsbrand', address='Hauptstraße 5')
    inc = room['incidents'][-1]
    act(room, ls, 1, 'dispatch', incident=inc['id'], vehicle='WB-2-LF20')
    return ls, gf, inc, room['vehicles']['WB-2-LF20']


def test_alarmiertes_spielerfahrzeug_wartet_auf_status_3(room, lage):
    ls, gf, inc, v = lage
    engine.update(room, NOW + 60)
    assert (v['phase'], v['status'], v['incident']) == ('wache', 2, inc['id'])
    act(room, gf, 2, 'status', now=NOW + 60, status=3)
    assert (v['phase'], v['status']) == ('anfahrt', 3)
    assert 'alarmed_at' not in v


def test_ankunft_und_rueckkehr_setzen_keinen_status(room, lage):
    ls, gf, inc, v = lage
    act(room, gf, 2, 'status', status=3)
    engine.update(room, v['phase_until'])
    assert (v['phase'], v['status']) == ('vorort', 3)
    assert room['radio'][-1]['message'] == 'Einsatzstelle erreicht – bitte Status 4 geben.'
    act(room, ls, 1, 'close', now=v['phase_at'], incident=inc['id'])
    assert (v['phase'], v['status']) == ('rueckfahrt', 3)
    engine.update(room, v['phase_until'])
    assert (v['phase'], v['status'], v['incident']) == ('wache', 3, None)
    # Ohne Status 1 oder 2 ist das Fahrzeug nicht frei.
    assert not engine._free(v)
    act(room, gf, 2, 'status', now=v['phase_at'], status=2)
    assert engine._free(v)


@pytest.mark.parametrize('status, fehler', [
    (4, 'Status 4 erst an der Einsatzstelle'),
    (2, 'Status 2 nur auf der Wache ohne Einsatz'),
    (6, 'Status 6 nur auf der Wache ohne Einsatz'),
    (1, 'Status 1 nicht während der Anfahrt'),
])
def test_unpassende_status_beim_alarm_abgelehnt(room, lage, status, fehler):
    ls, gf, inc, v = lage
    with pytest.raises(ValueError, match=fehler):
        act(room, gf, 2, 'status', status=status)


def test_status_3_ohne_alarm_abgelehnt(room):
    gf = join(room, 2, 'Ben')
    act(room, gf, 2, 'claim', vehicle='WB-2-LF20')
    with pytest.raises(ValueError, match='Status 3 nur nach einer Alarmierung'):
        act(room, gf, 2, 'status', status=3)


def test_aussteigen_waehrend_alarm_gesperrt(room, lage):
    ls, gf, inc, v = lage
    with pytest.raises(ValueError, match='Im Einsatz nicht aussteigen'):
        act(room, gf, 2, 'release')


def test_einsatzende_vor_dem_ausruecken_gibt_fahrzeug_frei(room, lage):
    ls, gf, inc, v = lage
    act(room, ls, 1, 'close', incident=inc['id'])
    assert (v['phase'], v['incident']) == ('wache', None)
    assert 'alarmed_at' not in v
    assert engine._free(v)


def test_alarmiertes_fahrzeug_ohne_spieler_rueckt_selbst_aus(room, lage):
    ls, gf, inc, v = lage
    v['owner'] = None  # z. B. Verbindung verloren
    engine.update(room, NOW + 1)
    assert (v['phase'], v['status']) == ('anfahrt', 3)
    engine.update(room, v['phase_until'])
    assert (v['phase'], v['status']) == ('vorort', 4)


def test_sprechwunsch_und_sprechaufforderung(room, lage):
    ls, gf, inc, v = lage
    act(room, gf, 2, 'status', now=NOW + 5, status=5)
    assert v['speak'] == NOW + 5 and v['status'] == 2  # Status 5 ändert den Fahrzeugstatus nicht
    assert room['radio'][-1]['message'] == 'Status 5 – Sprechwunsch (Ben).'
    with pytest.raises(ValueError, match='Leitstelle'):
        act(room, gf, 2, 'speak', vehicle='WB-2-LF20')
    act(room, ls, 1, 'speak', now=NOW + 8, vehicle='WB-2-LF20')
    assert 'speak' not in v and v['speak_ok'] == NOW + 8
    assert room['radio'][-1]['message'] == 'Florian WB 2 LF 20: Sprechaufforderung (J) – bitte sprechen.'
    with pytest.raises(ValueError, match='Kein Sprechwunsch'):
        act(room, ls, 1, 'speak', vehicle='WB-2-LF20')


def test_ki_leitstelle_beantwortet_sprechwunsch(room):
    gf = join(room, 2, 'Ben')
    act(room, gf, 2, 'claim', vehicle='WB-2-LF20')
    v = room['vehicles']['WB-2-LF20']
    act(room, gf, 2, 'status', status=5)
    engine.update(room, NOW + engine.AI_SPEAK_DELAY - 1)
    assert v.get('speak')
    engine.update(room, NOW + engine.AI_SPEAK_DELAY)
    assert 'speak' not in v and v['speak_ok'] == NOW + engine.AI_SPEAK_DELAY
    assert any(e['author'] == 'KI-Leitstelle' and 'Sprechaufforderung' in e['message'] for e in room['radio'])


def test_massnahmen_erst_nach_status_4(room, lage):
    ls, gf, inc, v = lage
    act(room, gf, 2, 'status', status=3)
    engine.update(room, v['phase_until'])
    with pytest.raises(ValueError, match='Zuerst Status 4'):
        act(room, gf, 2, 'work', now=v['phase_at'], incident=inc['id'])
    act(room, gf, 2, 'status', now=v['phase_at'], status=4)
    act(room, gf, 2, 'work', now=v['phase_at'], incident=inc['id'])
    assert inc['working']
