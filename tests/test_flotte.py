"""Echte Flotte der FF Westbummeln (game/flotte.py): Bestand, Rufnamen, Gespanne, Migration alter Räume."""
import json
import re
from collections import Counter

import pytest

from game import engine, flotte, persistence, rooms, strassen

NOW = 1_000_000.0

# Wachübersicht / AAO Abschnitt 2 (Stand 10.11.2026), GH1–GH5 je ein LF 10 (Entscheidung Lars).
PDF = {
    'LZ1': {'HLF 20': 2, 'TLF 3000': 1, 'LF 20': 1, 'DLK 23/12': 2, 'MTW': 2, 'Anh Tierrettung': 1},
    'LZ2': {'MLF': 2, 'TSF-W': 2, 'WLF': 2, 'Tankwagen': 1, 'SW 2000': 2, 'MTW': 4, 'AB-Schlauch': 1,
            'AB-Wasser': 1},
    'LZ3': {'HLF 20': 1, 'DLK 23/12': 1, 'ELW 1': 1, 'GW-L1': 1, 'MZF': 2, 'Anh Küche': 1, 'Anh Kühlung': 1},
    'LZ4': {'HLF 10': 2, 'RW': 2, 'GW-Öl': 1, 'WLF': 1, 'AB-Schiene': 1, 'GW HRett': 1, 'GW-G': 1},
    'LZ5': {'TLF 3000': 2, 'TLF 4000': 1, 'GTLF': 1, 'ATV': 2, 'KdoW Wald': 1, 'WLF': 1, 'LF 20 Wald': 1,
            'AB-Wald': 1, 'AB-Schlauch': 1, 'Anh Radlader': 1, 'Anh ATV Trans': 1},
    'LZ6': {'HLF 20': 1, 'RW': 1, 'MTW': 2, 'MZF Drohne': 2, 'ELW 1': 1, 'KdoW Lage': 1},
    'FTZ': {'KdoW KBM': 1, 'ELW 1': 2, 'ELW 2': 1, 'GW-Nachschub': 1, 'GW-MANV': 1, 'WLF': 2, 'AB-Dekon P': 1,
            'AB-Dekon G': 1, 'AB-Telelader': 1},
    **{f'GH{n}': {'LF 10': 1} for n in range(1, 6)},
}


@pytest.fixture
def room():
    r = engine.new_room('WB')
    r['weather_mode'] = 'manual'
    return r


def join(r, account, name='Spieler'):
    return engine.handle(r, {'action': 'join'}, account, name, False, NOW)['id']


def act(r, pid, account, action, now=NOW, **data):
    return engine.handle(r, {'action': action, 'id': pid, **data}, account, 'x', False, now)


def leitstelle(r):
    """Leitstelle plus zweiter Spieler (Mehrspieler: unbesetzte Fahrzeuge nur bei Bedarf laut Stichwort)."""
    ls = join(r, 1, 'Leitstelle')
    act(r, ls, 1, 'take_ls')
    gf = join(r, 2, 'GF')
    return ls, gf


def incident(r, ls, title='B3 · Großbrand', address='Marktplatz'):
    act(r, ls, 1, 'incident', title=title, address=address)
    return r['incidents'][-1]


# ------------------------------------------------------------------ Bestand und Rufnamen

def test_bestand_je_einheit_wie_im_pdf():
    for einheit, bestand in PDF.items():
        assert Counter(f['typ'] for f in flotte.fahrzeuge_der_einheit(einheit)) == bestand, einheit
    assert len(flotte.FAHRZEUGE) == sum(sum(b.values()) for b in PDF.values()) == 78
    assert set(flotte.EINHEITEN) == set(PDF)


def test_einheiten_laut_wachuebersicht():
    e = flotte.EINHEITEN
    assert [e[k]['name'] for k in ('LZ1', 'LZ2', 'LZ3', 'LZ4', 'LZ5', 'LZ6', 'FTZ')] == [
        'LZ 1 Mitte', 'LZ 2 Altstadt', 'LZ 3 Süd', 'LZ 4 Nord', 'LZ 5 West', 'LZ 6 Ost', 'FTZ Westbummeln']
    assert [e[f'LZ{n}']['fachgebiet'] for n in range(1, 7)] == [
        'Brandschutz', 'Wasserversorgung', 'Verpflegung', 'Technische Hilfeleistung', 'Vegetation', 'Lagedienst']
    assert e['FTZ']['standort_nr'] == 7
    assert e['FTZ']['pos'] == e['LZ2']['pos']  # FTZ steht bei LZ 2 Altstadt


def test_rufnamen_nach_schema_und_eindeutig():
    schema = re.compile(r'Florian Westbummeln (\d+) (\S.*)-(\d+)')
    rufnamen = [f['rufname'] for f in flotte.FAHRZEUGE]
    assert len(set(rufnamen)) == len(rufnamen)
    assert len({f['id'] for f in flotte.FAHRZEUGE}) == len(rufnamen)
    for f in flotte.FAHRZEUGE:
        match = schema.fullmatch(f['rufname'])
        assert match, f['rufname']
        assert int(match.group(1)) == flotte.EINHEITEN[f['einheit']]['standort_nr']
        assert re.fullmatch(r'[A-Za-z0-9-]+', f['id']), f['id']


def test_rufnamen_wie_im_funkrufnamen_verzeichnis():
    ruf = {f['id']: f['rufname'] for f in flotte.FAHRZEUGE}
    assert ruf['LZ1-HLF20-2'] == 'Florian Westbummeln 1 HLF 20-2'
    assert ruf['LZ1-DLK2312-1'] == 'Florian Westbummeln 1 DLK-1'
    assert ruf['LZ2-MTW-4'] == 'Florian Westbummeln 2 MTW-4'
    assert ruf['LZ4-GW-Oel-1'] == 'Florian Westbummeln 4 GW-Öl-1'
    assert ruf['LZ5-LF20Wald-1'] == 'Florian Westbummeln 5 LF 20-1'
    assert ruf['LZ5-KdoWWald-1'] == 'Florian Westbummeln 5 KdoW-1'
    assert ruf['LZ6-MZFDrohne-2'] == 'Florian Westbummeln 6 MZF-2'
    assert ruf['FTZ-KdoWKBM-1'] == 'Florian Westbummeln 7 KdoW-1'
    assert ruf['FTZ-ELW1-2'] == 'Florian Westbummeln 7 ELW 1-2'
    assert ruf['LZ2-AB-Schlauch-1'] == 'Florian Westbummeln 2 AB-Schlauch-1'


def test_hilfsfunktionen():
    assert {f['id'] for f in flotte.mit_faehigkeit('hubrettung')} == {'LZ1-DLK2312-1', 'LZ1-DLK2312-2',
                                                                      'LZ3-DLK2312-1'}
    assert [f['id'] for f in flotte.mit_faehigkeit('drohne', 'LZ6')] == ['LZ6-MZFDrohne-1', 'LZ6-MZFDrohne-2']
    assert flotte.zugfahrzeug_fuer('LZ1-AnhTierrettung-1')['id'] == 'LZ1-HLF20-1'
    assert flotte.zugfahrzeug_fuer('LZ4-AB-Schiene-1', frei=lambda vid: vid != 'LZ4-WLF-1')['id'] == 'FTZ-WLF-1'
    assert flotte.zugfahrzeug_fuer('LZ3-AnhKueche-1', frei=lambda vid: False) is None
    assert flotte.zugfahrzeug_fuer('LZ1-HLF20-1') is None  # Kfz brauchen keins
    for f in flotte.FAHRZEUGE:
        if flotte.kategorie(f['id']) != flotte.KFZ:
            assert flotte.zugfahrzeuge_fuer(f['id']), f['id']


def test_jede_einheit_erreicht_die_karte(room):
    """Jede Wache liegt am Straßennetz und ist kein Einsatzort."""
    for kennung, pos in engine.BASE.items():
        assert not engine.safe_location(pos), kennung
        route = strassen.route(pos, engine.locate('Marktplatz'))
        assert strassen.distance(route[0], route[1]) < .08, kennung  # kurze Zufahrt zur nächsten Straße


# ------------------------------------------------------------------ GF und Gespanne

def test_gf_uebernimmt_jedes_kfz_aber_keinen_anhaenger(room):
    gf = join(room, 2)
    for v in list(room['vehicles'].values()):
        if engine.is_kfz(v):
            act(room, gf, 2, 'claim', vehicle=v['id'])
            assert v['owner'] == gf
        else:
            with pytest.raises(ValueError, match='Zugfahrzeug'):
                act(room, gf, 2, 'claim', vehicle=v['id'])
    assert room['players'][gf]['vehicle'] == 'GH5-LF10-1'


def test_abrollbehaelter_faehrt_mit_wlf_als_gespann(room):
    ls, gf = leitstelle(room)
    act(room, gf, 2, 'claim', vehicle='LZ2-WLF-2')
    inc = incident(room, ls)
    act(room, ls, 1, 'dispatch', incident=inc['id'], vehicle='LZ2-AB-Wasser-1')
    ab, wlf = room['vehicles']['LZ2-AB-Wasser-1'], room['vehicles']['LZ2-WLF-2']
    # Das Spielerfahrzeug wird bevorzugt, obwohl LZ2-WLF-1 auch frei wäre.
    assert inc['assigned'] == ['LZ2-WLF-2', 'LZ2-AB-Wasser-1']
    assert wlf['towing'] == ab['id'] and ab['towed_by'] == wlf['id']
    assert room['radio'][-1]['message'].startswith('Alarm Florian Westbummeln 2 WLF-2 mit Florian Westbummeln 2 '
                                                   'AB-Wasser-1')
    # Spieler-WLF wartet auf Status 3 – der AB rückt nicht allein mit KI-Besatzung aus.
    engine.update(room, NOW + 5)
    assert ab['phase'] == wlf['phase'] == 'wache' and ab['incident'] == wlf['incident'] == inc['id']
    act(room, gf, 2, 'status', now=NOW + 5, status=3)
    assert ab['phase'] == wlf['phase'] == 'anfahrt' and ab['status'] == 3
    assert ab['phase_route'] == wlf['phase_route'] and ab['phase_until'] == wlf['phase_until']
    # Im Snapshot hängt der AB am WLF: keine eigene Route.
    shown = {v['id']: v for v in engine.snapshot(room, NOW)['vehicles']}
    assert 'phase_route' not in shown[ab['id']] and shown[ab['id']]['towed_by'] == wlf['id']

    engine.update(room, wlf['phase_until'])
    assert ab['phase'] == wlf['phase'] == 'vorort' and ab['status'] == 4
    act(room, gf, 2, 'status', now=wlf['phase_until'], status=4)
    act(room, ls, 1, 'close', now=wlf['phase_until'] + 1, incident=inc['id'])
    assert ab['phase'] == wlf['phase'] == 'rueckfahrt' and ab['phase_route'] == wlf['phase_route']
    engine.update(room, wlf['phase_until'])
    assert ab['phase'] == wlf['phase'] == 'wache'
    assert wlf['towing'] is None and ab['towed_by'] is None and ab['status'] == 2 and ab['incident'] is None


def test_einsatz_beendet_bevor_spieler_ausrueckt_loest_gespann(room):
    ls, gf = leitstelle(room)
    act(room, gf, 2, 'claim', vehicle='LZ1-HLF20-2')
    inc = incident(room, ls)
    act(room, ls, 1, 'dispatch', incident=inc['id'], vehicle='LZ1-AnhTierrettung-1')
    act(room, ls, 1, 'close', incident=inc['id'])
    hlf, anh = room['vehicles']['LZ1-HLF20-2'], room['vehicles']['LZ1-AnhTierrettung-1']
    assert hlf['towing'] is None and anh['towed_by'] is None
    assert hlf['incident'] is None and anh['incident'] is None and engine._free(anh)


def test_ohne_freies_zugfahrzeug_kein_alarm(room):
    ls, gf = leitstelle(room)
    inc = incident(room, ls)
    for wlf in ('LZ4-WLF-1', 'FTZ-WLF-1', 'FTZ-WLF-2'):
        room['vehicles'][wlf]['status'] = 6
    with pytest.raises(ValueError, match='Kein freies Zugfahrzeug'):
        act(room, ls, 1, 'dispatch', incident=inc['id'], vehicle='LZ4-AB-Schiene-1')
    assert inc['assigned'] == [] and room['vehicles']['LZ4-AB-Schiene-1']['phase'] == 'wache'


def test_abrollbehaelter_mit_wlf_vom_ftz(room):
    """Ist der WLF des eigenen LZ weg, holt ein WLF des FTZ den AB an dessen Wache ab und bringt ihn zurück."""
    ls, gf = leitstelle(room)
    inc = incident(room, ls, address='Werkstraße')
    room['vehicles']['LZ4-WLF-1']['status'] = 6
    act(room, ls, 1, 'dispatch', incident=inc['id'], vehicle='LZ4-AB-Schiene-1')
    ab, wlf = room['vehicles']['LZ4-AB-Schiene-1'], room['vehicles']['FTZ-WLF-1']
    assert wlf['towing'] == ab['id']
    lz4 = list(engine.BASE['LZ4'])
    assert wlf['phase_route'][0] == list(engine.BASE['FTZ']) and lz4 in wlf['phase_route']
    engine.update(room, wlf['phase_until'])
    act(room, ls, 1, 'close', now=wlf['phase_until'], incident=inc['id'])
    # Rückfahrt: der AB fährt zur LZ-4-Wache, der WLF über LZ 4 zurück zum FTZ.
    assert ab['phase_route'][-1] == lz4 and wlf['phase_route'][-1] == list(engine.BASE['FTZ'])
    assert ab['phase_until'] < wlf['phase_until']
    engine.update(room, ab['phase_until'])
    assert ab['phase'] == 'wache' and wlf['phase'] == 'rueckfahrt' and wlf['towing'] is None
    engine.update(room, wlf['phase_until'])
    assert wlf['phase'] == 'wache' and wlf['status'] == 2


def test_zugfahrzeug_waehlbar(room):
    ls, gf = leitstelle(room)
    inc = incident(room, ls)
    with pytest.raises(ValueError, match='nur mit HLF 20'):
        act(room, ls, 1, 'dispatch', incident=inc['id'], vehicle='LZ1-AnhTierrettung-1', zug='LZ1-MTW-1')
    act(room, ls, 1, 'dispatch', incident=inc['id'], vehicle='LZ1-AnhTierrettung-1', zug='LZ1-HLF20-2')
    assert room['vehicles']['LZ1-HLF20-2']['towing'] == 'LZ1-AnhTierrettung-1'


def test_anhaenger_zaehlen_nicht_als_fahrzeug_laut_stichwort(room):
    ls, gf = leitstelle(room)
    inc = incident(room, ls, title='F2 · Wohnungsbrand')
    act(room, ls, 1, 'dispatch', incident=inc['id'], vehicle='LZ3-AnhKueche-1')
    assert engine.ai_crew_block(room, inc) == ''  # 1 von 2 Fahrzeugen, der Anhänger zählt nicht
    act(room, ls, 1, 'dispatch', incident=inc['id'], vehicle='LZ1-HLF20-1')
    assert engine.ai_crew_block(room, inc).startswith('Bedarf gedeckt')


def test_ki_alarmiert_naechstes_loeschfahrzeug(room):
    gf = join(room, 2)
    room['incidents'].append(engine.new_incident('F1 · Kleinbrand', 'Werkstraße', engine.locate('Werkstraße'),
                                                 'Test', NOW))
    engine.run_ai(room, NOW)
    vid = room['incidents'][0]['assigned'][0]
    assert vid == 'GH5-LF10-1'  # das Gerätehaus Industrie liegt an der Werkstraße
    assert room['players'][gf]['vehicle'] is None


# ------------------------------------------------------------------ Snapshot

def test_snapshot_schickt_feste_felder_nur_einmal(room):
    gf = join(room, 2)
    full = engine.snapshot(room, NOW)
    assert full['fleet_full'] and full['vehicles'][0]['call'] == 'Florian Westbummeln 1 HLF 20-1'
    lean = act(room, gf, 2, 'state', fleet_rev=full['fleet_rev'])['state']
    assert not lean['fleet_full']
    assert lean['vehicles'][0] == {'id': 'LZ1-HLF20-1', 'status': 2, 'phase': 'wache'}
    assert len(json.dumps(lean)) < len(json.dumps(full)) / 2
    # Neuer Rufname: das Frontend bekommt die festen Felder wieder.
    room['admin'] = gf
    after = act(room, gf, 2, 'settings', fleet_rev=full['fleet_rev'], kind='vehicle', vehicle='LZ1-HLF20-1',
                call='HLF Mitte', seats=9)['state']
    assert after['fleet_full'] and after['vehicles'][0]['call'] == 'HLF Mitte'


# ------------------------------------------------------------------ Gespeicherte Räume (alte Flotte)

def alter_raum():
    """Raum, wie ihn die alte Flotte (6 Wachen × HLF 20, KdoW, LF 20) gespeichert hat."""
    r = engine.new_room('ALT')
    vehicles = {}
    for unit, pos in enumerate([(.235, .55), (.466, .51), (.565, .215), (.827, .46), (.548, .80), (.276, .15)],
                               start=1):
        for kind in ('HLF 20', 'KdoW', 'LF 20'):
            vid = f'WB-{unit}-{kind.replace(" ", "")}'
            vehicles[vid] = {'id': vid, 'call': f'Florian WB {unit} {kind}', 'unit': unit, 'kind': kind,
                             'seats': 9, 'base': list(pos), 'owner': None, 'status': 2, 'incident': None,
                             'phase': 'wache', 'phase_at': 0}
    vehicles['WB-9-Drehleiter'] = {**vehicles['WB-1-KdoW'], 'id': 'WB-9-Drehleiter'}
    r['vehicles'] = vehicles
    r.pop('fleet_rev')
    pid = 'spieler-ben'
    r['players'][pid] = {'id': pid, 'account': 2, 'name': 'Ben', 'vehicle': 'WB-1-HLF20', 'role': 'gf',
                         'last': NOW}
    v = vehicles['WB-1-HLF20']
    route = [[.235, .55], [.3, .55], [.41, .65]]
    v.update(owner=pid, status=3, incident='abc', phase='anfahrt', phase_at=NOW, phase_until=NOW + 12,
             phase_from=route[0], phase_to=route[-1], phase_route=route)
    inc = engine.new_incident('F2 · Wohnungsbrand', 'Marktplatz', [.41, .65], 'Anna', NOW)
    inc.update(id='abc', assigned=['WB-1-HLF20', 'WB-9-Drehleiter'])
    inc['sections']['Hauptabschnitt']['vehicles'] = ['WB-1-HLF20', 'WB-9-Drehleiter']
    r['incidents'].append(inc)
    return r


def speichern_laden(r, now=NOW):
    text = json.dumps({'version': persistence.VERSION, 'saved_at': now, 'rooms': {r['code']: r}, 'closed': {}})
    loaded, _ = persistence.parse(text, now)
    return loaded[r['code']]


def test_alter_raum_wird_auf_neue_flotte_umgestellt(caplog):
    r = speichern_laden(alter_raum())
    assert list(r['vehicles']) == [f['id'] for f in engine.FLEET]
    v = r['vehicles']['LZ5-LF20Wald-1']  # alte Wache 1 = heute LZ 5 West, gleiche Position
    assert v['owner'] == 'spieler-ben' and v['phase'] == 'anfahrt' and v['incident'] == 'abc'
    assert v['call'] == 'Florian Westbummeln 5 LF 20-1' and v['unit'] == 'LZ5' and v['kategorie'] == 'kfz'
    assert r['players']['spieler-ben']['vehicle'] == 'LZ5-LF20Wald-1'
    inc = r['incidents'][0]
    assert inc['assigned'] == ['LZ5-LF20Wald-1']  # unbekanntes Fahrzeug fällt weg
    assert inc['sections']['Hauptabschnitt']['vehicles'] == ['LZ5-LF20Wald-1']
    assert r['fleet_rev'] == 1
    assert 'Flotte umgestellt' in caplog.text and 'WB-9-Drehleiter' in caplog.text
    # Das Spiel läuft weiter: Ankunft, Rückfahrt zur neuen Wache.
    engine.update(r, NOW + 12)
    assert v['phase'] == 'vorort'
    engine._finish_incident(r, inc, NOW + 13)
    engine.update(r, v['phase_until'])
    assert v['phase'] == 'wache' and v['incident'] is None  # Status 2 gibt Ben selbst


def test_raum_mit_neuer_flotte_bleibt_unveraendert():
    r = engine.new_room('NEU')
    r['vehicles']['LZ1-HLF20-1']['call'] = 'Eigener Rufname'
    loaded = speichern_laden(json.loads(json.dumps(r)))
    assert loaded['fleet_rev'] == r['fleet_rev']
    assert loaded['vehicles']['LZ1-HLF20-1']['call'] == 'Eigener Rufname'


def test_kaputte_fahrzeuge_ergeben_frische_flotte(caplog):
    r = alter_raum()
    r['vehicles'] = ['kein', 'dict']
    r = speichern_laden(r)
    assert len(r['vehicles']) == 78 and all(v['phase'] == 'wache' for v in r['vehicles'].values())
    assert r['players']['spieler-ben']['vehicle'] is None and r['players']['spieler-ben']['role'] == 'none'
    assert r['incidents'][0]['assigned'] == []
    assert 'frische Flotte' in caplog.text


def test_alter_raum_ueber_die_datei(settings, tmp_path, monkeypatch):
    """Ganzer Weg wie beim Deploy: alte Datei liegt da, Server startet, Raum ist umgestellt."""
    path = tmp_path / 'rooms.json'
    settings.ROOM_STATE_FILE = str(path)
    monkeypatch.setattr(persistence, '_loaded', False)
    r = alter_raum()
    r.update(owner_account=1, owner_name='Anna', permanent=False, banned=[], kicked={}, last_seen=NOW)
    path.write_text(json.dumps({'version': persistence.VERSION, 'saved_at': NOW, 'rooms': {'ALT': r},
                                'closed': {}}), encoding='utf-8')
    assert persistence.load(NOW) == 1
    assert rooms.rooms['ALT']['players']['spieler-ben']['vehicle'] == 'LZ5-LF20Wald-1'
