"""Alarm- und Ausrückeordnung (game/aao.py) und ihre Anbindung an die Spiellogik."""
import json
from collections import Counter

import pytest

from game import aao, engine, persistence

NOW = 1_000_000.0
FLOTTE = aao.flotte_liste()


def pflicht(stichwort, ort='Schulstraße', fahrzeuge=FLOTTE):
    """Pflichtfahrzeuge als Multimenge (Einheit, Typ)."""
    v = aao.vorschlag(stichwort, fahrzeuge, ort=ort)
    return Counter((x['einheit'], aao._norm(x['typ'])) for x in v['fahrzeuge'] if not x['optional'])


def enthaelt(gross, klein):
    return not (klein - gross)


# ------------------------------------------------------------------ Daten

def test_alle_regeln_sind_lesbar_und_typen_gibt_es_in_der_einheit():
    bestand = {e: {aao._norm(t) for t in [x['typ'] for x in FLOTTE if x['einheit'] == e]} for e in aao.AAO_FLOTTE}
    for stichwort, daten in aao.STICHWORTE.items():
        for regel in aao.parse_alarm(daten['alarm'], stichwort):
            if regel['alle'] or regel['einheit'] in ('zuständig', 'alle LZ'):
                continue
            for einheit in regel['einheit'].split(' oder '):
                assert {aao._norm(t) for t in regel['typen']} & bestand[einheit], (stichwort, einheit, regel)


def test_alle_stichworte_aus_dem_pdf():
    assert set(aao.STICHWORTE) == {
        'B 1', 'B 2', 'B 2 Y', 'B 3', 'B 4', 'BMA', 'B Container', 'B Schiene', 'VEG 1', 'VEG 2', 'VEG 3',
        'TH 1', 'TH 2', 'TH Y', 'TH 3', 'TH Öl', 'TH Wasser', 'TH Sturm', 'TH Tier', 'TH Bahn', 'TH Drohne',
        'ABC 1', 'ABC 2', 'ABC 3', 'MANV 1', 'MANV 2', 'Verpflegung', 'Nachschub', 'Führung'}


def test_regeltext_mit_gruppe_sonderfall_und_bedingung():
    b1, = aao.parse_alarm('zuständig: 1 HLF/LF (LZ2: MLF)')
    assert b1['typen'] == ['HLF 20', 'HLF 10', 'LF 20', 'LF 10', 'LF 20 Wald'] and b1['sonder'] == {'LZ2': ['MLF']}
    dlk, = aao.parse_alarm('LZ1: 1 DLK 23/12 [Rettungshöhe über 8 m]')
    assert dlk['typen'] == ['DLK 23/12'] and dlk['optional'] and dlk['bedingung'] == 'Rettungshöhe über 8 m'


def test_einsatzbereiche_decken_alle_orte_ab():
    assert {name for name, _, _ in engine.PLACES} == set(aao.EINSATZBEREICHE)
    for zust, nachbar in aao.EINSATZBEREICHE.values():
        assert zust != nachbar and {zust, nachbar} <= set(aao.LOESCHZUEGE)
    assert aao.einsatzbereich('Kirchstraße 5') == ('LZ2', 'LZ1')
    assert aao.einsatzbereich('Flurstraße') == ('LZ4', 'LZ6')


# ------------------------------------------------------------------ Vererbung und Sonderfälle

def test_stufen_bauen_aufeinander_auf():
    assert aao.kette('B 3') == ['B 2', 'B 2 Y', 'B 3']
    b2, b2y, b3 = pflicht('B 2'), pflicht('B 2 Y'), pflicht('B 3')
    assert enthaelt(b3, b2y) and enthaelt(b2y, b2) and sum(b3.values()) > sum(b2y.values()) > sum(b2.values())
    assert enthaelt(pflicht('TH 3'), pflicht('TH Y')) and enthaelt(pflicht('TH Y'), pflicht('TH 2'))
    assert enthaelt(pflicht('ABC 3'), pflicht('ABC 2')) and enthaelt(pflicht('MANV 2'), pflicht('MANV 1'))
    assert enthaelt(pflicht('VEG 3'), pflicht('VEG 2'))


def test_zusaetzlich_heisst_mehr_fahrzeuge_derselben_einheit():
    # B 2: LZ 1 1x HLF 20, B 2 Y zusätzlich 1x HLF 20 → 2x HLF 20 aus LZ 1.
    assert pflicht('B 2')[('LZ1', 'hlf20')] == 1
    assert pflicht('B 2 Y')[('LZ1', 'hlf20')] == 2


def test_lz2_schickt_bei_b1_ein_mlf():
    v = aao.vorschlag('B 1', FLOTTE, ort='Kirchstraße')  # Einsatzbereich LZ 2
    assert v['zustaendig'] == 'LZ2'
    assert [(x['einheit'], x['typ'], x['status']) for x in v['fahrzeuge']] == [('LZ2', 'MLF', 'neu')]
    v = aao.vorschlag('B 1', FLOTTE, ort='Flurstraße')  # Einsatzbereich LZ 4
    assert [(x['einheit'], x['typ']) for x in v['fahrzeuge']] == [('LZ4', 'HLF 10')]


def test_wasserversorgung_ab_b2():
    for stichwort in ('B 2', 'B 2 Y', 'B 3', 'B 4'):
        assert any(e == 'LZ2' for e, _ in pflicht(stichwort)), stichwort
    assert not any(e == 'LZ2' for e, _ in pflicht('B 1'))


def test_besondere_regel_ergaenzt_fehlende_wasserversorgung(monkeypatch):
    b2 = dict(aao.STICHWORTE['B 2'], alarm='zuständig: 1 HLF/LF/TLF')
    monkeypatch.setitem(aao.STICHWORTE, 'B 2', b2)
    aao.regeln.cache_clear()
    try:
        regel = [r for r in aao.regeln('B 2') if r['einheit'] == 'LZ2']
        assert regel and regel[0]['quelle'] == 'Wasserversorgung'
    finally:
        aao.regeln.cache_clear()


@pytest.mark.parametrize('stichwort', ['B 2 Y', 'TH Y', 'VEG 2', 'ABC 2', 'B 3', 'TH 3', 'VEG 3', 'ABC 3'])
def test_elw1_aus_dem_ftz_ab_b2y(stichwort):
    assert pflicht(stichwort)[('FTZ', 'elw1')] >= 1


@pytest.mark.parametrize('stichwort, elw2', [('B 3', 1), ('TH 3', 1), ('B 4', 1), ('B 2 Y', 0), ('TH Y', 0)])
def test_elw2_ab_b3_und_th3(stichwort, elw2):
    assert min(pflicht(stichwort)[('FTZ', 'elw2')], 1) == elw2


@pytest.mark.parametrize('stichwort', ['B 3', 'VEG 3', 'TH 3', 'ABC 3', 'MANV 2'])
def test_kreisbrandmeister_und_presse_ab_b3(stichwort):
    assert pflicht(stichwort)[('FTZ', 'kdowkbm')] == 1
    assert aao.PRESSE in aao.meldungen(stichwort)
    assert aao.PRESSE not in aao.meldungen('B 2 Y')


def test_rettungsdienst_und_polizei_sind_virtuell():
    assert aao.meldungen('B 2 Y') == ['Rettungsdienst', 'Polizei']
    assert 'Bahnbetreiber' in aao.meldungen('TH Bahn')
    typen = {x['typ'] for x in aao.vorschlag('B 2 Y', FLOTTE, ort='Schulstraße')['fahrzeuge']}
    assert not typen & {'Rettungsdienst', 'Polizei'}


def test_abrollbehaelter_nur_mit_wlf():
    v = aao.vorschlag('B Schiene', FLOTTE, ort='Schulstraße')
    lz4 = [x['typ'] for x in v['fahrzeuge'] if x['einheit'] == 'LZ4']
    assert 'AB Schiene' in lz4 and 'WLF' in lz4


def test_optionale_fahrzeuge_sind_markiert():
    v = aao.vorschlag('BMA', FLOTTE, ort='Schulstraße')
    optional = {x['typ'] for x in v['fahrzeuge'] if x['optional']}
    assert optional == {'DLK 23/12', 'ELW 1'}


def test_ersatz_mit_hinweis_wenn_fahrzeug_belegt():
    busy = {x['id'] for x in FLOTTE if x['einheit'] == 'LZ3' and x['typ'] == 'DLK 23/12'}
    v = aao.vorschlag('B 2 Y', FLOTTE, ort='Schulstraße', frei=lambda x: x['id'] not in busy)
    ersatz = [x for x in v['fahrzeuge'] if x['status'] == 'ersatz' and x['typ'] == 'DLK 23/12']
    # LZ 1 hat zwei DLK, beide schon eingeplant → die DLK von LZ 3 fehlt.
    assert not ersatz and any(f['regel'] == 'LZ 3: DLK 23/12' and f['hinweis'] == 'nicht frei' for f in v['fehlt'])
    busy = {x['id'] for x in FLOTTE if x['einheit'] == 'LZ4' and x['typ'] == 'HLF 10'}
    v = aao.vorschlag('B 1', FLOTTE, ort='Flurstraße', frei=lambda x: x['id'] not in busy)
    (x,) = v['fahrzeuge']
    assert x['status'] == 'ersatz' and x['einheit'] == 'LZ6' and 'nicht frei' in x['hinweis']  # Nachbar-LZ


def test_ersatz_nimmt_spaeteren_plaetzen_nichts_weg():
    busy = {'LZ1-hlf20-1'}
    v = aao.vorschlag('B 3', FLOTTE, ort='Schulstraße', frei=lambda x: x['id'] not in busy)
    eigene = {(x['einheit'], x['status']) for x in v['fahrzeuge'] if x['typ'] == 'HLF 20' and x['regel'] != 'zusätzlich'
              and x['regel'].startswith(('LZ 3', 'LZ 6'))}
    assert eigene == {('LZ3', 'neu'), ('LZ6', 'neu')}


def test_hochstufen_schlaegt_nur_die_differenz_vor():
    b2 = aao.vorschlag('B 2', FLOTTE, ort='Schulstraße')
    ids = [x['id'] for x in b2['fahrzeuge']]
    b3 = aao.vorschlag('B 3', FLOTTE, ort='Schulstraße', bereits=ids, frei=lambda x: x['id'] not in ids)
    assert {x['id'] for x in b3['fahrzeuge'] if x['status'] == 'alarmiert'} == set(ids)
    neu = [x for x in b3['fahrzeuge'] if x['status'] != 'alarmiert']
    assert not {x['id'] for x in neu} & set(ids)
    assert len(neu) == sum(pflicht('B 3').values()) - len(ids)


# ------------------------------------------------------------------ Alte Stichworte

@pytest.mark.parametrize('alt, neu', [
    ('F1 · Kleinbrand', 'B 1'), ('F2 · Wohnungsbrand', 'B 2'), ('F3 · Dachstuhlbrand', 'B 3'),
    ('TH1 · Ölspur', 'TH 1'), ('TH2 · Verkehrsunfall', 'TH 2'), ('BMA · Brandmeldeanlage', 'BMA'),
    ('ABC1 · Gasgeruch', 'ABC 1'), ('TH · Wasserschaden', 'TH Wasser'), ('F1', 'B 1'), ('B 2 Y', 'B 2 Y'),
    ('b2y · klein geschrieben', 'B 2 Y'), ('Übung', None),
])
def test_alte_stichworte_werden_abgebildet(alt, neu):
    assert aao.stichwort_aus_titel(alt) == neu


def test_titel_alter_einsaetze_werden_umgeschrieben():
    assert aao.migriere_titel('F2 · Wohnungsbrand') == 'B 2 · Wohnungsbrand'
    assert aao.migriere_titel('TH1 · Ölspur') == 'TH 1 · Ölspur'
    assert aao.migriere_titel('F1') == 'B 1 · Kleinbrand'
    assert aao.migriere_titel('Übung Feuerwehrfest') == 'Übung Feuerwehrfest'


def test_gespeicherter_raum_bekommt_neue_stichworte():
    r = engine.new_room('ALT')
    r['incidents'].append({**engine.new_incident('x', 'Marktplatz', [.41, .65], 'Anna', NOW),
                           'title': 'F2 · Wohnungsbrand', 'stichwort': 'F2'})
    persistence.rooms.rooms['ALT'] = r
    try:
        text = persistence.dumps(NOW)
    finally:
        del persistence.rooms.rooms['ALT']
    loaded, _ = persistence.parse(text, NOW + 5)
    inc = loaded['ALT']['incidents'][0]
    assert (inc['title'], inc['stichwort']) == ('B 2 · Wohnungsbrand', 'B 2')
    assert json.dumps(loaded['ALT'])  # bleibt JSON-speicherbar


# ------------------------------------------------------------------ Spiellogik mit der AAO-Flotte

def aao_raum():
    """Raum mit der Fahrzeugliste aus der AAO (Testattrappe bis game/flotte.py da ist)."""
    r = engine.new_room('AAO', seed=1)
    r['weather_mode'] = 'manual'
    base = {**{f'LZ{n}': engine.BASE[n] for n in engine.BASE}, 'FTZ': engine.BASE[2]}
    r['vehicles'] = {v['id']: {**v, 'base': base[v['einheit']], 'owner': None, 'status': 2, 'incident': None,
                               'phase': 'wache', 'phase_at': 0, 'seats': 9} for v in FLOTTE}
    ls = join(r, 1, 'Anna')
    act(r, ls, 1, 'take_ls')
    return r, ls


def join(r, account, name, now=NOW):
    return engine.handle(r, {'action': 'join'}, account, name, False, now)['id']


def act(r, pid, account, action, now=NOW, **data):
    return engine.handle(r, {'action': action, 'id': pid, **data}, account, 'x', False, now)


def anlegen(r, ls, stichwort, ort):
    v = act(r, ls, 1, 'aao', stichwort=stichwort, address=ort)['vorschlag']
    ids = [x['id'] for x in v['fahrzeuge'] if not x['optional']]
    act(r, ls, 1, 'incident', title=f'{stichwort} · Test', address=ort, vehicles=ids)
    return r['incidents'][-1], ids


@pytest.mark.parametrize('stichwort', ['B 1', 'B 2 Y', 'B 3', 'TH 2'])
def test_leitstelle_legt_an_und_alarmiert_mit_einem_klick(stichwort):
    r, ls = aao_raum()
    inc, ids = anlegen(r, ls, stichwort, 'Schulstraße')
    assert inc['stichwort'] == stichwort and inc['assigned'] == ids
    assert all(r['vehicles'][i]['phase'] == 'anfahrt' for i in ids)
    assert engine.needed_vehicles(inc) == sum(pflicht(stichwort).values()) + len(
        [f for f in aao.vorschlag(stichwort, FLOTTE, ort='Schulstraße')['fehlt'] if not f['optional']])
    assert r['radio'][-1 if stichwort in ('B 1', 'TH 2') else -2]['message'].startswith(f'Alarm {stichwort} · Test')


def test_virtuelle_kraefte_als_funkmeldung():
    r, ls = aao_raum()
    anlegen(r, ls, 'B 2 Y', 'Schulstraße')
    assert r['radio'][-1]['message'].endswith('über die Leitstelle verständigt – Rettungsdienst, Polizei.')


def test_hochstufen_alarmiert_nur_die_differenz():
    r, ls = aao_raum()
    inc, ids = anlegen(r, ls, 'B 2', 'Schulstraße')
    v = act(r, ls, 1, 'aao', incident=inc['id'], stichwort='B 3')['vorschlag']
    neu = [x['id'] for x in v['fahrzeuge'] if x['status'] != 'alarmiert' and not x['optional']]
    assert neu and not set(neu) & set(ids)
    act(r, ls, 1, 'stufe', incident=inc['id'], stichwort='B 3', vehicles=neu)
    assert inc['title'] == 'B 3 · Test' and inc['stichwort'] == 'B 3'
    assert inc['assigned'] == ids + neu
    assert any('hochgestuft B 2 → B 3' in x['message'] for x in r['radio'])
    # Erneut B 3: nichts mehr vorzuschlagen außer Optionalem / Fehlendem.
    v = act(r, ls, 1, 'aao', incident=inc['id'], stichwort='B 3')['vorschlag']
    assert all(x['status'] == 'alarmiert' for x in v['fahrzeuge'] if not x['optional'])


def test_standard_meldebild_wechselt_beim_hochstufen_mit():
    r, ls = aao_raum()
    act(r, ls, 1, 'incident', title='B 1', address='Marktplatz', vehicles=[])
    inc = r['incidents'][-1]
    assert inc['title'] == 'B 1 · Kleinbrand'
    act(r, ls, 1, 'stufe', incident=inc['id'], stichwort='B 2', vehicles=[])
    assert inc['title'] == 'B 2 · Mittelbrand'


def test_herabstufen_alarmiert_nichts():
    r, ls = aao_raum()
    inc, ids = anlegen(r, ls, 'B 2', 'Schulstraße')
    act(r, ls, 1, 'stufe', incident=inc['id'], stichwort='B 1', vehicles=[])
    assert inc['stichwort'] == 'B 1' and inc['assigned'] == ids
    assert any('herabgestuft B 2 → B 1' in x['message'] for x in r['radio'])


def test_vorschlag_nur_fuer_die_leitstelle():
    r, ls = aao_raum()
    gf = join(r, 2, 'Ben')
    with pytest.raises(ValueError, match='Nur die besetzte Leitstelle'):
        act(r, gf, 2, 'aao', stichwort='B 1', address='Marktplatz')
    with pytest.raises(ValueError, match='Stichwort aus der AAO'):
        act(r, ls, 1, 'aao', stichwort='F9', address='Marktplatz')


def test_vorschlag_veraendert_den_raum_nicht():
    r, ls = aao_raum()
    rev = r['rev']
    act(r, ls, 1, 'aao', stichwort='B 3', address='Marktplatz')
    assert r['rev'] == rev and r['incidents'] == []


def test_spielerfahrzeug_wird_bevorzugt():
    r, ls = aao_raum()
    gf = join(r, 2, 'Ben')
    act(r, gf, 2, 'claim', vehicle='LZ1-hlf20-2')
    v = act(r, ls, 1, 'aao', stichwort='B 2', address='Schulstraße')['vorschlag']
    lz1 = [x['id'] for x in v['fahrzeuge'] if x['einheit'] == 'LZ1' and x['typ'] == 'HLF 20']
    assert lz1 == ['LZ1-hlf20-2']


def test_leitstelle_darf_aao_mit_ki_besatzung_alarmieren_im_mehrspieler():
    r, ls = aao_raum()
    gf = join(r, 2, 'Ben')
    act(r, gf, 2, 'claim', vehicle='LZ5-tlf3000-1')  # freies Spielerfahrzeug, nicht in der AAO
    inc, ids = anlegen(r, ls, 'B 2', 'Schulstraße')
    assert inc['assigned'] == ids and all(not r['vehicles'][i]['owner'] for i in ids)


# ------------------------------------------------------------------ KI-Leitstelle

def test_ki_alarmiert_allein_nach_aao():
    r = engine.new_room('KI', seed=3)
    r['weather_mode'] = 'manual'
    r['vehicles'] = aao_raum()[0]['vehicles']
    join(r, 1, 'Anna')
    engine.update(r, NOW)
    inc = r['incidents'][0]
    v = aao.vorschlag(inc['stichwort'], FLOTTE, ort=inc['address'])
    assert len(inc['assigned']) == len([x for x in v['fahrzeuge'] if not x['optional']])


def ki_stichworte(n, seed=5):
    r = engine.new_room('KI', seed=seed)
    result = []
    for _ in range(n):
        r['incidents'] = []
        engine._ai_new_incident(r, NOW)
        inc = r['incidents'][0]
        result.append((inc['stichwort'], inc['address']))
    return result


def test_ki_stichworte_sind_gewichtet_und_reproduzierbar():
    sample = ki_stichworte(3000)
    assert sample == ki_stichworte(3000)
    counts = Counter(s for s, _ in sample)
    assert all(s in aao.STICHWORTE for s in counts)
    haeufig = counts['B 1'] + counts['TH 1'] + counts['BMA']
    assert haeufig > .5 * len(sample)
    for selten in ('B 3', 'ABC 2', 'ABC 3', 'MANV 1', 'MANV 2', 'TH 3', 'VEG 3'):
        assert counts[selten] < .02 * len(sample), selten
    assert counts['B 1'] > counts['B 2'] > counts['B 3']


def test_ki_stichworte_passen_zum_ort():
    sample = ki_stichworte(3000)
    veg = {ort for s, ort in sample if s.startswith('VEG')}
    assert veg and all(set(aao.ORTE[o]) & {'feld', 'wald'} for o in veg)
    assert not {s for s, _ in sample} & {'B Schiene', 'TH Bahn'}  # keine Bahnstrecke auf der Karte
