"""Maßnahmen je Einsatz (PR A: F1). Zeit läuft nur über `now` (siehe test_spiellogik.py)."""
import json

import pytest

from game import engine, katalog, massnahmen, persistence, rooms

NOW = 1_000_000.0


@pytest.fixture
def room():
    r = engine.new_room('WB', seed=1)
    r['weather_mode'] = 'manual'
    return r


def join(r, account, name, now=NOW):
    return engine.handle(r, {'action': 'join'}, account, name, False, now)['id']


def act(r, pid, account, action, now=NOW, **data):
    return engine.handle(r, {'action': action, 'id': pid, **data}, account, 'x', False, now)


def laufen(r, von, bis):
    """Sekundenweise vorspulen, alle Spieler bleiben online. Liefert den letzten Zeitpunkt."""
    t = von
    while True:
        t = min(t, bis)
        for p in r['players'].values():
            p['last'] = t
        engine.update(r, t)
        if t >= bis:
            return bis
        t += 1


def bis_dass(r, t, bedingung, hoechstens):
    """Sekundenweise weiter, bis die Bedingung gilt (höchstens so viele Sekunden). Liefert den Zeitpunkt."""
    for schritt in range(1, hoechstens):
        laufen(r, t + schritt, t + schritt)
        if bedingung():
            return t + schritt
    return t + hoechstens


def funk(r):
    return [x['message'] for x in r['radio']]


def f1_vor_ort(r, titel='F1 · Gartenhütte', vehicle='WB-2-LF20'):
    """Leitstelle Anna, GF Ben auf vehicle; F1 an der Hauptstraße, alarmiert, Fahrzeug steht vor Ort."""
    ls, gf = join(r, 1, 'Anna'), join(r, 2, 'Ben')
    act(r, ls, 1, 'take_ls')
    act(r, gf, 2, 'claim', vehicle=vehicle)
    act(r, ls, 1, 'incident', title=titel, address='Hauptstraße 5')
    inc = r['incidents'][-1]
    act(r, ls, 1, 'dispatch', incident=inc['id'], vehicle=vehicle)
    v = r['vehicles'][vehicle]
    da = laufen(r, NOW, v['phase_until'])
    assert v['phase'] == 'vorort'
    return ls, gf, inc, v, da


def starten(r, gf, inc, key, now):
    return act(r, gf, 2, 'massnahme', now=now, incident=inc['id'], key=key)


# ------------------------------------------------------------ Katalog

def test_katalog_ist_stimmig():
    for stichwort, eintrag in katalog.KATALOG.items():
        keys = set(eintrag['massnahmen'])
        assert set(eintrag['ki']) <= keys, stichwort
        for m in eintrag['massnahmen'].values():
            for b in [*m.get('hart', ()), *m.get('weich', ()), *m.get('ki_warten', ())]:
                assert b in keys or b in katalog.BEDINGUNGEN, (stichwort, b)
            assert katalog.FAHRZEUGTYPEN and m['platz'] in ('fuehrung', 'trupp')
            # Jede Maßnahme kann mindestens ein Fahrzeugtyp.
            assert massnahmen._typen_mit(m['braucht']), m['name']
        assert any(m.get('pflicht') for m in eintrag['massnahmen'].values())


def test_nur_f1_bekommt_massnahmen():
    f1 = engine.new_incident('F1 · Kleinbrand', 'Marktplatz', [.41, .65], 'x', NOW)
    f2 = engine.new_incident('F2 · Wohnungsbrand', 'Marktplatz', [.41, .65], 'x', NOW)
    frei = engine.new_incident('TH · Wasserschaden', 'Marktplatz', [.41, .65], 'x', NOW)
    assert f1['stichwort'] == 'F1' and 'mn' in f1
    assert 'mn' not in f2 and 'mn' not in frei


@pytest.mark.parametrize('titel, variante', [
    ('F1 · Mülltonnenbrand', 'muelltonne'), ('F1 · Gartenhütte', 'gartenhuette'), ('F1 · PKW-Brand', 'pkw'),
])
def test_variante_aus_titel(titel, variante):
    assert engine.new_incident(titel, 'Marktplatz', [.41, .65], 'x', NOW)['mn']['variante'] == variante


def test_variante_zufaellig_aber_fest_je_einsatz():
    inc = {'id': 'abcd1234', 'title': 'F1 · Kleinbrand'}
    assert massnahmen.init_einsatz(inc, NOW)
    wiederholt = {'id': 'abcd1234', 'title': 'F1 · Kleinbrand'}
    massnahmen.init_einsatz(wiederholt, NOW)
    assert inc['mn']['variante'] == wiederholt['mn']['variante'] in ('muelltonne', 'gartenhuette', 'hecke')


def test_trupps_aus_sitzplaetzen():
    assert massnahmen.trupps({'seats': 3}) == 1
    assert massnahmen.trupps({'seats': 6}) == 2
    assert massnahmen.trupps({'seats': 9}) == 3


# ------------------------------------------------------------ F1 richtig gespielt

def test_richtige_reihenfolge_loescht_f1_ohne_eskalation(room):
    ls, gf, inc, v, t = f1_vor_ort(room)
    starten(room, gf, inc, 'erkunden', t)
    starten(room, gf, inc, 'wasser', t)
    t = laufen(room, t + 1, t + 10)
    assert inc['mn']['variante'] == 'gartenhuette'
    assert any('Erkundung: Gartenhütte' in m for m in funk(room))
    starten(room, gf, inc, 'angriff', t)
    starten(room, gf, inc, 'angriff', t)
    with pytest.raises(ValueError, match='Läuft bereits'):
        starten(room, gf, inc, 'angriff', t)
    t = bis_dass(room, t, lambda: inc['mn']['aus'], 120)
    assert inc['mn']['aus'] and inc['mn']['zaehler']['wasser_aus'] == 0
    with pytest.raises(ValueError, match='Feuer ist schon aus'):
        starten(room, gf, inc, 'angriff', t)
    starten(room, gf, inc, 'nachloeschen', t)
    laufen(room, t + 1, t + 21)
    assert inc['closed'] and inc['bilanz']['stufe_max'] == 0
    assert inc['bilanz']['sterne'] == 3 and inc['stichwort'] == 'F1'
    assert any(m.startswith('📋 Einsatzbilanz F1 · Hauptstraße 5: ★★★') for m in funk(room))
    assert 'mn' not in inc
    assert v['phase'] == 'rueckfahrt'


def test_muelltonne_geht_mit_tankwasser(room):
    ls, gf, inc, v, t = f1_vor_ort(room, 'F1 · Mülltonnenbrand')
    starten(room, gf, inc, 'erkunden', t)
    t = laufen(room, t + 1, t + 10)
    starten(room, gf, inc, 'angriff', t)
    t = bis_dass(room, t, lambda: inc['mn']['aus'], 120)
    assert inc['mn']['aus'] and not inc['mn']['wasser']
    assert inc['mn']['zaehler']['wasser_aus'] == 0 and inc['mn']['stufe_max'] == 0


# ------------------------------------------------------------ Eskalation

def test_angriff_ohne_wasser_warnt_eskaliert_und_wird_eingefangen(room):
    ls, gf, inc, v, t = f1_vor_ort(room, 'F1 · Gartenhütte')
    starten(room, gf, inc, 'erkunden', t)
    t = laufen(room, t + 1, t + 10)
    starten(room, gf, inc, 'angriff', t)
    mn = inc['mn']
    # 1. Warnung nach ⅔ des Tanks (LF 20: 40 s)
    t = bis_dass(room, t, lambda: f'E1:{v["id"]}' in mn['gewarnt'], 60)
    assert any(w['regel'] == 'E1' and w['fz'] == v['id'] for w in mn['warnungen'])
    assert v['tank'] == pytest.approx(2000 / 3, abs=60)  # Füllstand gehört zum Fahrzeug (Liter)
    snap = next(i for i in engine.snapshot(room, t)['incidents'] if i['id'] == inc['id'])
    assert any('Tank nur noch' in w['text'] and w['bis'] for w in snap['massnahmen']['warnungen'])
    assert snap['massnahmen']['lage']['tank'][v['id']]['loescht']
    # 2. Wasser aus → 🟡
    t = laufen(room, t + 1, t + 15)
    assert mn['zaehler']['wasser_aus'] == 1 and massnahmen.stufe(inc) == 1
    assert any('Wasser aus' in m for m in funk(room))
    # 3. Feuer wächst doppelt → Warnung E2 → Stichworterhöhung F1 → F2 mit Nachforderung
    t = bis_dass(room, t, lambda: mn['eskaliert'], 200)
    assert any('Feuer droht' in m for m in funk(room))
    assert inc['stichwort'] == 'F2' and inc['title'] == 'F2 · Gartenhütte'
    assert massnahmen.stufe(inc) == 2
    assert sorted(massnahmen.offene_nachforderungen(inc, room['vehicles'])) == ['HLF 20', 'KdoW']
    assert any('Stichworterhöhung F1 → F2' in m and 'Nachforderung: 1 HLF 20, 1 KdoW' in m for m in funk(room))
    # Die Leitstelle darf die Nachforderung auch mit KI-Besatzung schicken.
    assert engine.ai_crew_block(room, inc) == ''
    act(room, ls, 1, 'dispatch', now=t, incident=inc['id'], vehicle='WB-2-HLF20')
    assert massnahmen.offene_nachforderungen(inc, room['vehicles']) == ['KdoW']
    # 4. Einfangen: Wasserversorgung → Angriff läuft wieder → Brand sinkt → Lage unter Kontrolle
    starten(room, gf, inc, 'wasser', t)
    starten(room, gf, inc, 'angriff', t)
    t = bis_dass(room, t, lambda: not mn['aktiv'], 200)
    assert mn['wasser'] and not mn['aktiv']
    assert any('Lage wieder unter Kontrolle' in m for m in funk(room))
    t = bis_dass(room, t, lambda: mn['aus'], 200)
    if not massnahmen._laeuft(mn, 'nachloeschen'):  # das HLF (KI-Besatzung) ist evtl. schneller
        starten(room, gf, inc, 'nachloeschen', t)
    laufen(room, t + 1, t + 25)
    assert inc['closed']
    assert any(x['author'] == 'KI-Gruppenführer' for x in room['radio'])  # HLF hat mitgearbeitet
    b = inc['bilanz']
    assert b['stichwort'] == 'F1' and b['stichwort_ende'] == 'F2' and b['stufe_max'] == 2
    assert b['wasser_aus'] == 1 and b['sterne'] < 3 and b['tipp']


def test_ki_leitstelle_erfuellt_nachforderung(room):
    ls, gf, inc, v, t = f1_vor_ort(room, 'F1 · Gartenhütte')
    act(room, ls, 1, 'leave_ls', now=t)  # ab jetzt KI-Leitstelle
    room['ai_last'] = t + 10_000  # keine neuen KI-Einsätze
    inc['mn']['brand'] = 39.9
    laufen(room, t + 1, t + 1)
    assert inc['stichwort'] == 'F2'
    laufen(room, t + 2, t + engine.NACHFORDERUNG_KI_DELAY)
    assert len(inc['assigned']) == 1
    laufen(room, t + engine.NACHFORDERUNG_KI_DELAY + 1, t + engine.NACHFORDERUNG_KI_DELAY + 2)
    kinds = sorted(room['vehicles'][vid]['kind'] for vid in inc['assigned'])
    assert kinds == ['HLF 20', 'KdoW', 'LF 20']
    assert massnahmen.offene_nachforderungen(inc, room['vehicles']) == []


# ------------------------------------------------------------ Tank am Fahrzeug

def test_tank_bleibt_leer_bis_zur_wache_und_hydrant_fuellt_nach(room):
    ls, gf, inc, v, t = f1_vor_ort(room, 'F1 · Mülltonnenbrand')
    assert v['tank'] == 2000
    starten(room, gf, inc, 'erkunden', t)
    t = laufen(room, t + 1, t + 10)
    starten(room, gf, inc, 'angriff', t)
    t = bis_dass(room, t, lambda: inc['mn']['aus'], 120)
    rest = v['tank']
    assert 0 < rest < 2000  # nur so viel verbraucht, wie gelöscht wurde
    starten(room, gf, inc, 'nachloeschen', t)
    t = laufen(room, t + 1, t + 21)
    assert inc['closed'] and v['phase'] == 'rueckfahrt'
    assert v['tank'] == rest  # auf der Rückfahrt bleibt der Tank so leer
    snap = {x['id']: x for x in engine.snapshot(room, t)['vehicles']}
    assert snap[v['id']]['tank'] == rest and engine.snapshot(room, t)['tank_voll']['LF 20'] == 2000
    laufen(room, t + 1, v['phase_until'])
    assert v['phase'] == 'wache' and v['tank'] == 2000  # auf der Wache wieder voll


def test_hydrant_fuellt_tank_wieder_auf(room):
    ls, gf, inc, v, t = f1_vor_ort(room, 'F1 · Gartenhütte')
    v['tank'] = 300.0  # kommt vorbelastet vom letzten Einsatz
    starten(room, gf, inc, 'wasser', t)
    t = laufen(room, t + 1, t + 31)
    assert inc['mn']['wasser']
    laufen(room, t + 1, t + 10)
    assert v['tank'] > 300 + 9 * 30


def test_vorbelasteter_tank_ist_schnell_leer(room):
    ls, gf, inc, v, t = f1_vor_ort(room, 'F1 · Mülltonnenbrand')
    v['tank'] = 200.0  # 4 s Löschzeit
    starten(room, gf, inc, 'angriff', t)
    bis_dass(room, t, lambda: inc['mn']['zaehler']['wasser_aus'], 40)
    assert inc['mn']['zaehler']['wasser_aus'] == 1 and v['tank'] == 0


def test_stichwort_nach_nrw_schema(monkeypatch):
    monkeypatch.setitem(katalog.KATALOG, 'B 1', katalog.KATALOG['F1'])
    inc = engine.new_incident('B 1 · Kleinbrand', 'Marktplatz', [.41, .65], 'x', NOW)
    assert inc['stichwort'] == 'B 1' and inc['mn']['katalog'] == 'B 1'
    assert massnahmen.stichwort_aus_titel('b1 · Mülltonne') == 'B 1'
    assert massnahmen.stichwort_aus_titel('TH 1 · Ölspur') == ''


# ------------------------------------------------------------ Regeln und Rechte

def test_harte_voraussetzung_blockiert(room):
    ls, gf, inc, v, t = f1_vor_ort(room)
    with pytest.raises(ValueError, match='🔒 Erst muss das Feuer aus sein'):
        starten(room, gf, inc, 'nachloeschen', t)
    snap = next(i for i in engine.snapshot(room, t)['incidents'] if i['id'] == inc['id'])
    nach = next(m for m in snap['massnahmen']['massnahmen'] if m['key'] == 'nachloeschen')
    assert nach['hart'] == ['Erst muss das Feuer aus sein']
    angriff = next(m for m in snap['massnahmen']['massnahmen'] if m['key'] == 'angriff')
    assert len(angriff['weich']) == 2 and not angriff['hart']


def test_kein_freier_trupp_und_fuehrung(room):
    ls, gf, inc, v, t = f1_vor_ort(room)
    v['seats'] = 5  # Staffel: 2 Trupps
    starten(room, gf, inc, 'erkunden', t)
    starten(room, gf, inc, 'wasser', t)
    starten(room, gf, inc, 'angriff', t)
    with pytest.raises(ValueError, match='Kein freier Trupp'):
        starten(room, gf, inc, 'angriff', t)
    with pytest.raises(ValueError, match='Läuft bereits'):
        starten(room, gf, inc, 'erkunden', t)


def test_kdow_kann_nur_erkunden(room):
    ls, gf, inc, v, t = f1_vor_ort(room, vehicle='WB-2-KdoW')
    with pytest.raises(ValueError, match='🔒 Nur HLF 20 oder LF 20'):
        starten(room, gf, inc, 'wasser', t)
    starten(room, gf, inc, 'erkunden', t)


def test_nur_gf_vor_ort_darf(room):
    ls, gf = join(room, 1, 'Anna'), join(room, 2, 'Ben')
    act(room, ls, 1, 'take_ls')
    act(room, gf, 2, 'claim', vehicle='WB-2-LF20')
    act(room, ls, 1, 'incident', title='F1 · Kleinbrand', address='Hauptstraße 5')
    inc = room['incidents'][-1]
    with pytest.raises(ValueError, match='Nur ein GF'):
        act(room, ls, 1, 'massnahme', incident=inc['id'], key='erkunden')
    act(room, ls, 1, 'dispatch', incident=inc['id'], vehicle='WB-2-LF20')
    with pytest.raises(ValueError, match='Einsatzstelle erreichen'):
        starten(room, gf, inc, 'erkunden', NOW)
    with pytest.raises(ValueError, match='Meine Einsatzstelle'):
        laufen(room, NOW, room['vehicles']['WB-2-LF20']['phase_until'])
        act(room, gf, 2, 'work', now=room['vehicles']['WB-2-LF20']['phase_until'], incident=inc['id'])


def test_abbrechen_gibt_trupp_frei(room):
    ls, gf, inc, v, t = f1_vor_ort(room)
    starten(room, gf, inc, 'wasser', t)
    act(room, gf, 2, 'massnahme_stop', now=t, incident=inc['id'], key='wasser')
    assert not massnahmen._aktiv(inc['mn'])
    with pytest.raises(ValueError, match='läuft nicht'):
        act(room, gf, 2, 'massnahme_stop', now=t, incident=inc['id'], key='wasser')


def test_wetter_verlaengert_dauer(room):
    room['weather'] = 'Regen'
    ls, gf, inc, v, t = f1_vor_ort(room)
    starten(room, gf, inc, 'wasser', t)
    i = inc['mn']['m'][0]
    assert i['ende'] - i['start'] == pytest.approx(30 / .85)


def test_snapshot_verraet_variante_erst_nach_erkunden(room):
    ls, gf, inc, v, t = f1_vor_ort(room)
    snap = next(i for i in engine.snapshot(room, t)['incidents'] if i['id'] == inc['id'])
    assert 'mn' not in snap and snap['massnahmen']['variante'] is None
    assert snap['massnahmen']['lage']['brand'] is None and snap['massnahmen']['lage']['brand_grob']
    assert 'gartenhuette' not in json.dumps(snap)
    assert len(json.dumps(snap)) < 4000
    starten(room, gf, inc, 'erkunden', t)
    laufen(room, t + 1, t + 11)
    snap = next(i for i in engine.snapshot(room, t + 11)['incidents'] if i['id'] == inc['id'])
    assert snap['massnahmen']['variante'] == 'Gartenhütte' and snap['massnahmen']['lage']['brand'] > 0


def test_leitstelle_bricht_ab_bilanz_ohne_sterne(room):
    ls, gf, inc, v, t = f1_vor_ort(room)
    act(room, ls, 1, 'close', now=t, incident=inc['id'])
    assert inc['bilanz']['abgebrochen'] and inc['bilanz']['sterne'] == 0
    assert any('abgebrochen' in m for m in funk(room))


# ------------------------------------------------------------ KI-Gruppenführer

def ki_einsatz(inc_id, variante, kind='LF 20', start=NOW):
    """Ein Katalog-Einsatz mit einem KI-Fahrzeug vor Ort, ohne Raum (reine Logik)."""
    v = {'id': 'WB-1-X', 'call': 'Florian WB 1', 'kind': kind, 'seats': 9, 'phase': 'vorort',
         'incident': inc_id, 'phase_at': start + 15, 'owner': None}
    inc = {'id': inc_id, 'title': f'F1 · {variante}', 'assigned': [v['id']]}
    massnahmen.init_einsatz(inc, start)
    return inc, {v['id']: v}


def ki_spielt(inc, vehicles, start=NOW, dauer=400):
    entscheidungen = []
    for t in range(int(start) + 15, int(start) + dauer):
        massnahmen.tick(inc, vehicles, t)
        if massnahmen.fertig(inc):
            return t, entscheidungen
        entscheidungen += [m for _, m in massnahmen.ki_waehlen(inc, list(vehicles.values()), t)]
    return None, entscheidungen


@pytest.mark.parametrize('variante', ['Mülltonne', 'Gartenhütte', 'Hecke', 'PKW'])
@pytest.mark.parametrize('kind', ['LF 20', 'HLF 20'])
def test_ki_gf_loest_f1_mit_einem_fahrzeug(variante, kind):
    for n in range(15):
        inc, vehicles = ki_einsatz(f'id{n:04d}', variante, kind)
        ende, _ = ki_spielt(inc, vehicles)
        assert ende is not None, (variante, kind, n)
        assert inc['mn']['stufe_max'] < 2, (variante, kind, n)


def test_ki_gf_ist_reproduzierbar_und_macht_manchmal_fehler():
    verlauf = {}
    for n in range(40):
        a = ki_spielt(*ki_einsatz(f'k{n}', 'Gartenhütte'))[1]
        b = ki_spielt(*ki_einsatz(f'k{n}', 'Gartenhütte'))[1]
        assert a == b
        verlauf[n] = a
    # Musterlösung: erst Erkunden + Wasser, dann Angriff. Ab und zu greift die KI zu früh an (15 %).
    assert any(v[1].endswith('Wasserversorgung aufbauen.') for v in verlauf.values())
    assert any('Angriffsleitung' in v[1] for v in verlauf.values())


def test_ki_gf_faengt_wasser_aus_ein():
    inc, vehicles = ki_einsatz('fang', 'Gartenhütte')
    v = next(iter(vehicles.values()))
    massnahmen.tick(inc, vehicles, NOW + 15)
    # Mensch hat nur einen Angriff ohne Wasser gestartet, dann übernimmt die KI.
    massnahmen.starten(inc, v, 'angriff', NOW + 15)
    ende, entscheidungen = ki_spielt(inc, vehicles, NOW + 1)
    assert ende and any('Wasserversorgung' in e for e in entscheidungen)


def test_ki_gf_loest_f1_im_raum(room, monkeypatch):
    monkeypatch.setattr(engine, 'AI_INCIDENT_TYPES', [('F1 · Kleinbrand', 1)])
    join(room, 1, 'Anna')  # allein: KI-Leitstelle + KI-Besatzung
    laufen(room, NOW, NOW + 200)
    inc = room['incidents'][0]
    assert inc['closed'] and inc['bilanz']['sterne'] >= 1
    assert any(m.startswith('📋 Einsatzbilanz F1') for m in funk(room))
    assert any(x['author'] == 'KI-Gruppenführer' for x in room['radio'])


# ------------------------------------------------------------ Speichern und Laden

T = 1_800_000_000.0


@pytest.fixture
def state_file(tmp_path, settings, monkeypatch):
    path = tmp_path / 'rooms.json'
    settings.ROOM_STATE_FILE = str(path)
    monkeypatch.setattr(persistence, '_loaded', True)
    monkeypatch.setattr(persistence, '_stopped', False)
    monkeypatch.setattr(persistence, '_last_fingerprint', None)
    return path


def test_raum_mit_laufenden_massnahmen_ist_speicher_und_ladbar(state_file):
    r = engine.new_room('MASSN', seed=3)
    r['weather_mode'] = 'manual'
    rooms.rooms['MASSN'] = r
    try:
        ls, gf = join(r, 1, 'Anna', T), join(r, 2, 'Ben', T)
        act(r, ls, 1, 'take_ls', now=T)
        act(r, gf, 2, 'claim', now=T, vehicle='WB-2-LF20')
        act(r, ls, 1, 'incident', now=T, title='F1 · Gartenhütte', address='Hauptstraße 5')
        inc = r['incidents'][-1]
        act(r, ls, 1, 'dispatch', now=T, incident=inc['id'], vehicle='WB-2-LF20')
        t = laufen(r, T, r['vehicles']['WB-2-LF20']['phase_until'])
        starten(r, gf, inc, 'erkunden', t)
        starten(r, gf, inc, 'wasser', t)
        t = laufen(r, t + 1, t + 5)
        brand = inc['mn']['brand']
        ende = next(i['ende'] for i in inc['mn']['m'] if i['key'] == 'wasser')
        assert persistence.save(force=True, now=t)
        rooms.rooms.clear()
        assert persistence.load(t + 90) == 1
        r = rooms.rooms['MASSN']
        inc = r['incidents'][-1]
        # Die Ausfallzeit zählt nicht: Maßnahme endet 90 s später, das Feuer ist nicht gewachsen.
        assert next(i['ende'] for i in inc['mn']['m'] if i['key'] == 'wasser') == ende + 90
        assert inc['mn']['zeiten']['notruf'] == T + 90
        laufen(r, t + 91, t + 91)
        assert inc['mn']['brand'] == pytest.approx(brand + .2, abs=.01)
        t = laufen(r, t + 92, t + 120)
        assert inc['mn']['wasser']
        starten(r, gf, inc, 'angriff', t)
        t = bis_dass(r, t, lambda: inc['mn']['aus'], 200)
        starten(r, gf, inc, 'nachloeschen', t)
        laufen(r, t + 1, t + 25)
        assert inc['closed'] and inc['bilanz']['stufe_max'] == 0
        json.loads(persistence.dumps(t + 25))
    finally:
        rooms.rooms.clear()
