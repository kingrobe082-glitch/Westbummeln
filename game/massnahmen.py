"""Maßnahmen je Einsatz: Trupps, Voraussetzungen, Lage, Eskalation, KI-GF und Einsatzbilanz.

Reine Logik ohne Django und ohne Funk: Funktionen, die etwas zu melden haben, liefern eine Liste von
(Absender, Text); game/engine.py sendet sie über emit(). Die Daten stehen in game/katalog.py, das Konzept in
docs/KONZEPT-MASSNAHMEN.md.

Der ganze Zustand liegt in inc['mn'] und ist JSON (Räume werden gespeichert, siehe game/persistence.py).
Zufall (Variante, KI-Fehler) entsteht jedes Mal neu aus Einsatz-ID und Zähler – nie als Objekt im Raum.
Zeitpunkte heißen notruf/alarm/eintreffen/feuer_aus/start/ende/nachgefordert/at und stehen in
persistence.TIME_KEYS.
"""
import random

from game.katalog import (
    BEDINGUNGEN,
    BRAND_AUS,
    BRAND_WETTER,
    FAHRZEUGTYPEN,
    KATALOG,
    LOESCHRATE,
    OHNE_ERKUNDEN_AUFBAU,
    STUFEN,
    TANK_SEKUNDEN_JE_LITER,
    TRUPPS_JE_SITZE,
    WASSER_AUS_WACHSTUM,
)

LAUFEND = ('laeuft', 'loescht', 'wartet')
KI_FEHLER = .15  # Schwierigkeit „Normal“: so oft nimmt die KI die zweitbeste Maßnahme (Konzept 5.3)
SCHRITT = 1.0  # Sekunden je Rechenschritt in tick()


# ------------------------------------------------------------------ Anlegen

def stichwort_aus_titel(title):
    """'F1 · Kleinbrand' → 'F1'. Ohne „·“ zählt das erste Wort."""
    head = str(title).split('·', 1)[0].strip()
    return head.split()[0].upper() if head else ''


def init_einsatz(inc, now, seed=None):
    """Katalog-Zustand anlegen, wenn das Stichwort im Katalog steht. Liefert True bei Katalog-Einsätzen.

    seed: Grundlage für Variante und KI-Zufall (KI-Leitstelle: aus dem Raum-Seed, damit ein Raum mit gleichem
    Seed gleich verläuft); sonst die Einsatz-ID."""
    key = stichwort_aus_titel(inc['title'])
    eintrag = KATALOG.get(key)
    if not eintrag:
        return False
    seed = str(inc['id'] if seed is None else seed)
    variante = _variante(inc, eintrag, seed)
    lage = {**eintrag['lage'], **eintrag['varianten'][variante]}
    inc['stichwort'] = key
    inc['mn'] = {
        'katalog': key, 'stichwort_start': key, 'variante': variante, 'seed': seed,
        'brand': float(lage['brand']), 'wachstum': lage['wachstum'], 'aus': False, 'wasser': False,
        'tank': {}, 'm': [], 'aktiv': {}, 'stufe_max': 0, 'warnungen': [], 'gewarnt': [],
        'eskaliert': False, 'nachforderungen': [], 'rate': 0.0,
        'zeiten': {'notruf': now}, 'zaehler': {'wasser_aus': 0}, 'ki_schritt': 0, 'ki_fz': [],
    }
    inc['updated'] = now
    return True


def _variante(inc, eintrag, seed):
    """Variante aus dem Titel („Mülltonnenbrand“ → Mülltonne), sonst zufällig, aber fest je Einsatz-ID."""
    title = inc['title'].lower()
    for key, v in eintrag['varianten'].items():
        if any(word in title for word in v.get('titel', ())):
            return key
    keys = sorted(k for k, v in eintrag['varianten'].items() if v.get('zufall', True))
    return random.Random(f'{seed}:variante').choice(keys)


def ist_katalog(inc):
    return 'mn' in inc


def _eintrag(mn):
    return KATALOG[mn['katalog']]


# ------------------------------------------------------------------ Fahrzeuge und Plätze

def faehigkeiten(v):
    return FAHRZEUGTYPEN.get(v['kind'], {}).get('faehigkeiten', ())


def trupps(v):
    seats = v.get('seats', 9)
    return next((n for limit, n in TRUPPS_JE_SITZE if seats <= limit), TRUPPS_JE_SITZE[-1][1])


def tank_voll(v):
    return FAHRZEUGTYPEN.get(v['kind'], {}).get('tank', 0) * TANK_SEKUNDEN_JE_LITER


def vor_ort(inc, vehicles):
    return [vehicles[vid] for vid in inc['assigned']
            if vid in vehicles and vehicles[vid]['phase'] == 'vorort' and vehicles[vid]['incident'] == inc['id']]


def _aktiv(mn):
    return [i for i in mn['m'] if i['status'] in LAUFEND]


def _fertig(mn, key):
    return any(i['key'] == key and i['status'] == 'fertig' for i in mn['m'])


def _laeuft(mn, key):
    return any(i['key'] == key and i['status'] in LAUFEND for i in mn['m'])


def _erfuellt(mn, bedingung):
    return mn['aus'] if bedingung == BRAND_AUS else _fertig(mn, bedingung)


def _bedingung_text(eintrag, bedingung):
    if bedingung in BEDINGUNGEN:
        return BEDINGUNGEN[bedingung]
    return f'Erst {eintrag["massnahmen"][bedingung]["name"]}'


def _platz(mn, v, platz):
    """Nächster freier Platz des Fahrzeugs: 0 = Führung, 1… = Trupp-Nummer; None = keiner frei."""
    belegt = {i['trupp'] for i in _aktiv(mn) if i['fz'] == v['id'] and i['platz'] == platz}
    if platz == 'fuehrung':
        return None if belegt else 0
    return next((n for n in range(1, trupps(v) + 1) if n not in belegt), None)


def _typen_mit(braucht):
    return [kind for kind, t in FAHRZEUGTYPEN.items() if all(f in t['faehigkeiten'] for f in braucht)]


def pruefen(inc, v, key):
    """Darf v die Maßnahme key jetzt starten? Liefert (Grund, Platz); Grund '' = ja."""
    mn = inc['mn']
    eintrag = _eintrag(mn)
    m = eintrag['massnahmen'].get(key)
    if not m:
        return 'Unbekannte Maßnahme', None
    if v['id'] not in inc['assigned'] or v['incident'] != inc['id'] or v['phase'] != 'vorort':
        return 'Zuerst muss dein Fahrzeug die Einsatzstelle erreichen', None
    if _fertig(mn, key) and m.get('wirkung') != 'loeschen':
        return 'Bereits erledigt', None
    if _entfaellt(mn, m):
        return 'Das Feuer ist schon aus', None
    if sum(1 for i in _aktiv(mn) if i['key'] == key) >= m.get('max', 1):
        return 'Läuft bereits', None
    if not all(f in faehigkeiten(v) for f in m['braucht']):
        return f'🔒 Nur {" oder ".join(_typen_mit(m["braucht"]))}', None
    for bedingung in m.get('hart', ()):
        if not _erfuellt(mn, bedingung):
            return f'🔒 {_bedingung_text(eintrag, bedingung)}', None
    platz = _platz(mn, v, m['platz'])
    if platz is None:
        return ('Führung ist schon beschäftigt' if m['platz'] == 'fuehrung' else 'Kein freier Trupp'), None
    return '', platz


def _entfaellt(mn, m):
    """Löschen und Wasserversorgung braucht nach „Feuer aus“ niemand mehr."""
    return mn['aus'] and m.get('wirkung') in ('loeschen', 'wasser')


def _platz_name(instanz):
    return 'Führung' if instanz['platz'] == 'fuehrung' else f'Trupp {instanz["trupp"]}'


def starten(inc, v, key, now, arbeit=1, ki=False):
    """Maßnahme mit dem nächsten freien Platz von v starten. Wirft ValueError; liefert den Funktext."""
    grund, platz = pruefen(inc, v, key)
    if grund:
        raise ValueError(grund)
    mn = inc['mn']
    eintrag = _eintrag(mn)
    m = eintrag['massnahmen'][key]
    # Dauer steht ab dem Start fest (Wetter wie bei den Fahrten).
    dauer = m['dauer'] / (arbeit or 1)
    fehlt = [b for b in m.get('weich', ()) if not _erfuellt(mn, b)]
    if m.get('wirkung') == 'loeschen' and 'erkunden' in fehlt:
        dauer += OHNE_ERKUNDEN_AUFBAU
    instanz = {'key': key, 'fz': v['id'], 'platz': m['platz'], 'trupp': platz, 'status': 'laeuft',
               'start': now, 'ende': now + dauer, 'ki': ki}
    mn['m'].append(instanz)
    if m.get('wirkung') == 'loeschen' and v['id'] not in mn['tank']:
        mn['tank'][v['id']] = tank_voll(v)
    inc['working'] = True
    text = f'{_platz_name(instanz)}: {m["name"]}.'
    if fehlt:
        text += ' ⚠️ ' + ', '.join(eintrag.get('weich_text', {}).get(b, b) for b in fehlt)
    return text


def abbrechen(inc, v, key):
    """Laufende Maßnahme des Fahrzeugs v abbrechen; der Platz wird frei, der Fortschritt ist weg."""
    mn = inc['mn']
    instanz = next((i for i in reversed(mn['m'])
                    if i['key'] == key and i['fz'] == v['id'] and i['status'] in LAUFEND), None)
    if not instanz:
        raise ValueError('Maßnahme läuft nicht (oder gehört nicht zu deinem Fahrzeug)')
    mn['m'].remove(instanz)
    return f'{_platz_name(instanz)}: {_eintrag(mn)["massnahmen"][key]["name"]} abgebrochen.'


# ------------------------------------------------------------------ Lage fortschreiben

def tick(inc, vehicles, now, wetter='Sonnig', arbeit=1):
    """Lage und Maßnahmen bis now fortschreiben. Liefert Funksprüche [(Absender, Text)]."""
    mn = inc['mn']
    meldungen = []
    zeiten = mn['zeiten']
    da = vor_ort(inc, vehicles)
    if 'eintreffen' not in zeiten and da:
        zeiten['eintreffen'] = min(v['phase_at'] for v in da)
    # Fahrzeuge, die abgezogen wurden, nehmen ihre Trupps mit.
    ids = {v['id'] for v in da}
    mn['m'] = [i for i in mn['m'] if i['status'] not in LAUFEND or i['fz'] in ids]
    t = inc.get('updated', now)
    if now - t > 600 * SCHRITT:  # sehr lange Pause (z. B. Test): gröber rechnen
        schritt = (now - t) / 600
    else:
        schritt = SCHRITT
    while t < now - 1e-9:
        t1 = min(now, t + schritt)
        _schritt(inc, vehicles, t1, t1 - t, wetter, meldungen)
        t = t1
    inc['updated'] = now
    inc['progress'] = fortschritt(inc)
    return meldungen


def _call(vehicles, vid):
    return vehicles.get(vid, {}).get('call', vid)


def _schritt(inc, vehicles, t, h, wetter, meldungen):
    mn = inc['mn']
    eintrag = _eintrag(mn)
    vorher = dict(mn['aktiv'])
    # a) fertige Maßnahmen
    for i in sorted((i for i in mn['m'] if i['status'] == 'laeuft' and i['ende'] <= t), key=lambda i: i['ende']):
        _fertigstellen(inc, vehicles, i, t, meldungen)
    # b) Brand: Wachstum gegen Löschen
    if not mn['aus']:
        loeschend = [i for i in mn['m'] if i['status'] == 'loescht']
        for i in loeschend:
            if mn['wasser']:
                continue
            mn['tank'][i['fz']] = max(0.0, mn['tank'].get(i['fz'], 0) - h)
        wachstum = mn['wachstum'] * BRAND_WETTER.get(wetter, 1)
        if 'E1' in mn['aktiv']:
            wachstum *= WASSER_AUS_WACHSTUM
        rate = wachstum - LOESCHRATE * len(loeschend)
        mn['rate'] = rate
        mn['brand'] = min(100.0, max(0.0, mn['brand'] + rate * h))
        for i in loeschend:
            if not mn['wasser'] and mn['tank'][i['fz']] <= 0:
                i['status'] = 'wartet'
                if 'E1' not in mn['aktiv']:
                    mn['zaehler']['wasser_aus'] += 1
                    mn['aktiv']['E1'] = 1
                    _warnung_weg(mn, 'E1')
                    meldungen.append((_call(vehicles, i['fz']),
                                      '🟡 Wasser aus! Angriffstrupp geht zurück – Wasserversorgung aufbauen.'))
        if mn['brand'] <= 0:
            mn['aus'] = True
            mn['rate'] = 0.0
            mn['zeiten']['feuer_aus'] = t
            for i in mn['m']:
                if i['key'] in eintrag['massnahmen'] and eintrag['massnahmen'][i['key']].get('wirkung') == 'loeschen' \
                        and i['status'] in LAUFEND:
                    i.update(status='fertig', ende=t)
            meldungen.append(('Einsatzleitung', '🔥 Feuer aus. Nachlöschen und Kontrolle.'))
    # c) Regeln
    _regel_e1(mn, vehicles, t, meldungen)
    _regel_e2(inc, vehicles, t, meldungen)
    if vorher and not mn['aktiv']:
        meldungen.append(('Einsatzleitung', '🟢 Lage wieder unter Kontrolle.'))
    mn['stufe_max'] = max(mn['stufe_max'], stufe(inc))


def _fertigstellen(inc, vehicles, i, t, meldungen):
    mn = inc['mn']
    eintrag = _eintrag(mn)
    m = eintrag['massnahmen'][i['key']]
    call = _call(vehicles, i['fz'])
    if m.get('wirkung') == 'loeschen' and not mn['aus']:
        hat_wasser = mn['wasser'] or mn['tank'].get(i['fz'], 0) > 0
        i['status'] = 'loescht' if hat_wasser else 'wartet'
        if hat_wasser:
            quelle = 'Wasser vom Hydranten' if mn['wasser'] else 'Tankwasser'
            meldungen.append((call, f'{_platz_name(i)}: Angriffsleitung steht, Wasser marsch ({quelle}).'))
        else:
            meldungen.append((call, f'{_platz_name(i)}: Angriffsleitung steht, aber kein Wasser – Tank leer.'))
            if 'E1' not in mn['aktiv']:
                mn['zaehler']['wasser_aus'] += 1
                mn['aktiv']['E1'] = 1
        return
    i['status'] = 'fertig'
    if i['key'] == 'erkunden':
        variante = eintrag['varianten'][mn['variante']]
        meldungen.append((call, f'Erkundung: {variante["meldung"]} 🔥 {round(mn["brand"])}'))
    elif m.get('wirkung') == 'wasser':
        mn['wasser'] = True
        wartend = [w for w in mn['m'] if w['status'] == 'wartet']
        for w in wartend:
            w['status'] = 'loescht'
        meldungen.append((call, 'Wasserversorgung steht.' + (' Angriff läuft wieder.' if wartend else '')))
    else:
        meldungen.append((call, f'{m["name"]} erledigt.'))


def _warnen(mn, regel, text, t):
    if regel in mn['gewarnt']:
        return False
    mn['gewarnt'].append(regel)
    mn['warnungen'].append({'regel': regel, 'text': text, 'at': t})
    return True


def _warnung_weg(mn, regel):
    mn['warnungen'] = [w for w in mn['warnungen'] if w['regel'] != regel]


def _regel_e1(mn, vehicles, t, meldungen):
    """E1 Angriff ohne Wasserversorgung: Warnung nach ⅔ des Tanks, dann „Wasser aus“."""
    if mn['wasser']:
        _warnung_weg(mn, 'E1')
        mn['aktiv'].pop('E1', None)
        return
    for i in mn['m']:
        if i['status'] != 'loescht':
            continue
        voll = tank_voll(vehicles[i['fz']]) if i['fz'] in vehicles else 0
        if voll and mn['tank'].get(i['fz'], 0) <= voll / 3 and 'E1' not in mn['aktiv']:
            if _warnen(mn, 'E1', 'Tank nur noch ⅓ – Wasserversorgung?', t):
                meldungen.append((_call(vehicles, i['fz']), '⚠️ Angriffstrupp: Tank nur noch ⅓ – Wasserversorgung?'))
    if not any(i['status'] == 'loescht' for i in mn['m']):
        _warnung_weg(mn, 'E1')
    if 'E1' in mn['aktiv'] and not any(i['status'] == 'wartet' for i in mn['m']):
        mn['aktiv'].pop('E1')


def _regel_e2(inc, vehicles, t, meldungen):
    """E2 Brand erreicht die Schwelle: Warnung, dann Stichworterhöhung mit Nachforderung; einfangen durch Löschen."""
    mn = inc['mn']
    esk = _eintrag(mn).get('eskalation')
    if not esk:
        return
    brand = mn['brand']
    if not mn['eskaliert']:
        if brand >= esk['schwelle'] - esk['warnung'] and mn['rate'] > 0:
            if _warnen(mn, 'E2', f'Feuer droht auf {esk["ziel"]} überzugreifen!', t):
                meldungen.append(('Einsatzleitung', f'⚠️ Feuer droht auf {esk["ziel"]} überzugreifen!'))
        elif brand < esk['schwelle'] - esk['warnung'] - 3 and 'E2' in mn['gewarnt']:
            _warnung_weg(mn, 'E2')
            mn['gewarnt'].remove('E2')
        if brand >= esk['schwelle']:
            _eskalieren(inc, vehicles, esk, t, meldungen)
    elif 'E2' in mn['aktiv'] and brand <= esk['einfangen']:
        mn['aktiv'].pop('E2')


def _eskalieren(inc, vehicles, esk, t, meldungen):
    mn = inc['mn']
    alt = inc['stichwort']
    neu = esk['stichwort']
    mn['eskaliert'] = True
    mn['aktiv']['E2'] = 2
    _warnung_weg(mn, 'E2')
    inc['stichwort'] = neu
    rest = inc['title'].split('·', 1)[1].strip() if '·' in inc['title'] else inc['title']
    inc['title'] = f'{neu} · {rest}'[:90]
    mn['nachforderungen'] = list(esk['aao'])
    mn['nachgefordert'] = t
    offen = offene_nachforderungen(inc, vehicles)
    text = f'🟠 Stichworterhöhung {alt} → {neu}: Feuer greift auf {esk["ziel"]} über.'
    if offen:
        text += ' Nachforderung: ' + ', '.join(f'{n} {kind}' for kind, n in _zaehlen(offen))
    meldungen.append(('Einsatzleitung', text + '.'))


def _zaehlen(kinds):
    result = []
    for kind in kinds:
        if result and result[-1][0] == kind:
            result[-1] = (kind, result[-1][1] + 1)
        else:
            result.append((kind, 1))
    return result


def offene_nachforderungen(inc, vehicles):
    """Fahrzeugtypen aus der Nachforderung, die noch nicht alarmiert sind (Mehrfachnennung möglich)."""
    mn = inc.get('mn')
    if not mn or not mn['nachforderungen']:
        return []
    vorhanden = [vehicles[vid]['kind'] for vid in inc['assigned']
                 if vid in vehicles and vehicles[vid]['incident'] == inc['id']]
    offen = []
    for kind in sorted(mn['nachforderungen']):
        if kind in vorhanden:
            vorhanden.remove(kind)
        else:
            offen.append(kind)
    return offen


def stufe(inc):
    return max(inc['mn']['aktiv'].values(), default=0)


def fertig(inc):
    """Alle Pflicht-Maßnahmen erledigt?"""
    mn = inc['mn']
    massnahmen = _eintrag(mn)['massnahmen']
    return all(_fertig(mn, key) for key, m in massnahmen.items() if m.get('pflicht'))


def fortschritt(inc):
    """Abgeleiteter Fortschritt in % für Liste, Abschnitte und KI-Leitstelle."""
    if fertig(inc):
        return 100
    mn = inc['mn']
    massnahmen = _eintrag(mn)['massnahmen']
    erledigt = sum(1 for key in massnahmen if _fertig(mn, key))
    return min(95, round(100 * erledigt / len(massnahmen)))


# ------------------------------------------------------------------ KI-Gruppenführer

def _kandidaten(inc):
    """Musterreihenfolge, Gegenmaßnahmen zu Warnungen und Eskalationen zuerst (Konzept 5.3)."""
    mn = inc['mn']
    zuerst = []
    regeln = {w['regel'] for w in mn['warnungen']} | set(mn['aktiv'])
    if 'E1' in regeln:
        zuerst.append('wasser')
    if 'E2' in regeln:
        zuerst.append('angriff')
    return list(dict.fromkeys(zuerst + _eintrag(mn)['ki']))


def _ki_weich_ok(mn, m):
    """Die KI wartet, bis weiche Voraussetzungen fertig sind oder wenigstens laufen (ki_warten: fertig)."""
    if any(not _erfuellt(mn, b) for b in m.get('ki_warten', ())):
        return False
    return all(_erfuellt(mn, b) or _laeuft(mn, b) for b in m.get('weich', ()))


def ki_waehlen(inc, fahrzeuge, now, arbeit=1):
    """Freie Plätze der KI-Fahrzeuge mit Maßnahmen belegen. Liefert Funksprüche."""
    mn = inc['mn']
    massnahmen = _eintrag(mn)['massnahmen']
    meldungen = []
    for v in sorted(fahrzeuge, key=lambda v: v['id']):
        for _ in range(6):  # höchstens so viele Entscheidungen je Fahrzeug und Abfrage
            moeglich = [k for k in _kandidaten(inc) if not pruefen(inc, v, k)[0]]
            gut = [k for k in moeglich if _ki_weich_ok(mn, massnahmen[k])]
            if not gut:
                break
            wahl = gut[0]
            rng = random.Random(f'{mn["seed"]}:ki:{mn["ki_schritt"]}')
            mn['ki_schritt'] += 1
            # Fehler nur bei gleicher Platzart: statt Wasserversorgung z. B. zu früh der Angriff.
            zweite = [k for k in moeglich if k != wahl and massnahmen[k]['platz'] == massnahmen[wahl]['platz']]
            if zweite and rng.random() < KI_FEHLER:
                wahl = zweite[0]
            text = starten(inc, v, wahl, now, arbeit, ki=True)
            meldungen.append(('KI-Gruppenführer', f'{v["call"]} – {text}'))
    return meldungen


# ------------------------------------------------------------------ Einsatzbilanz

def _mmss(sekunden):
    if sekunden is None:
        return '–'
    sekunden = max(0, round(sekunden))
    return f'{sekunden // 60}:{sekunden % 60:02d}'


def bilanz(inc, now, abgebrochen=False):
    """Kurze Einsatzbilanz (Konzept 6) für Funk und Einsatzliste. Bleibt nur im Raum."""
    mn = inc['mn']
    eintrag = _eintrag(mn)
    z = mn['zeiten']

    def spanne(a, b):
        return z[b] - z[a] if a in z and b in z else None

    z_ende = {**z, 'ende': now}
    dauer = {
        'alarm': spanne('notruf', 'alarm'),
        'anfahrt': spanne('alarm', 'eintreffen'),
        'loeschen': spanne('eintreffen', 'feuer_aus'),
        'gesamt': z_ende['ende'] - z['notruf'],
    }
    arbeit = now - z['eintreffen'] if 'eintreffen' in z else None
    b = {
        'stichwort': mn['stichwort_start'], 'stichwort_ende': inc['stichwort'], 'abgebrochen': abgebrochen,
        'variante': eintrag['varianten'][mn['variante']]['name'], 'dauer': dauer,
        'stufe_max': mn['stufe_max'], 'wasser_aus': mn['zaehler']['wasser_aus'],
        'punkte': None, 'sterne': 0, 'tipp': None,
    }
    if not abgebrochen:
        punkte = 100 - {0: 0, 1: 10, 2: 20, 3: 35}[mn['stufe_max']] - 5 * mn['zaehler']['wasser_aus']
        if mn['stufe_max'] == 0 and arbeit is not None:
            richtzeit = eintrag['richtzeit']
            punkte += round(15 * min(1, max(0, (richtzeit - arbeit) / (richtzeit / 2))))
        if dauer['alarm'] is not None and dauer['alarm'] < 20:
            punkte += 5
        punkte = min(120, max(0, punkte))
        b['punkte'] = punkte
        b['sterne'] = 3 if punkte >= 90 else 2 if punkte >= 65 else 1
    tipps = eintrag.get('tipps', {})
    if mn['zaehler']['wasser_aus']:
        b['tipp'] = tipps.get('wasser_aus')
    elif mn['eskaliert']:
        b['tipp'] = tipps.get('eskalation')
    elif not _fertig(mn, 'erkunden'):
        b['tipp'] = tipps.get('ohne_erkunden')
    return b


def bilanz_text(inc):
    b = inc['bilanz']
    stichwort = b['stichwort'] + (f' → {b["stichwort_ende"]}' if b['stichwort_ende'] != b['stichwort'] else '')
    if b['abgebrochen']:
        kopf = f'📋 Einsatzbilanz {stichwort} · {inc["address"]}: abgebrochen'
    else:
        kopf = f'📋 Einsatzbilanz {stichwort} · {inc["address"]}: {"★" * b["sterne"]}{"☆" * (3 - b["sterne"])} ' \
               f'{b["punkte"]} Punkte'
    d = b['dauer']
    teile = [kopf, f'Notruf→Alarm {_mmss(d["alarm"])}', f'Anfahrt {_mmss(d["anfahrt"])}',
             f'Feuer aus nach {_mmss(d["loeschen"])}', f'Gesamt {_mmss(d["gesamt"])}',
             'keine Eskalation' if not b['stufe_max'] else f'höchste Stufe {STUFEN[b["stufe_max"]][0]}']
    if b['wasser_aus']:
        teile.append(f'Wasser aus {b["wasser_aus"]}×')
    return ' · '.join(teile) + '.' + (f' 💡 {b["tipp"]}' if b['tipp'] else '')


# ------------------------------------------------------------------ Anzeige

def _brand_grob(brand):
    return 'klein' if brand < 20 else 'mittel' if brand < 35 else 'groß'


def snapshot(inc, vehicles, now):
    """Was das Frontend über einen offenen Katalog-Einsatz sieht. Die Variante erst nach dem Erkunden."""
    mn = inc['mn']
    eintrag = _eintrag(mn)
    erkundet = _fertig(mn, 'erkunden')
    s = stufe(inc)
    da = vor_ort(inc, vehicles)
    liste = []
    for key, m in eintrag['massnahmen'].items():
        liste.append({
            'key': key, 'name': m['name'], 'icon': m.get('icon', ''), 'dauer': m['dauer'], 'platz': m['platz'],
            'pflicht': bool(m.get('pflicht')), 'max': m.get('max', 1), 'info': m.get('info', ''),
            'braucht': list(m['braucht']), 'typen': _typen_mit(m['braucht']),
            'fertig': _fertig(mn, key) and (m.get('wirkung') != 'loeschen' or mn['aus']),
            'laufend': sum(1 for i in _aktiv(mn) if i['key'] == key),
            'hart': [_bedingung_text(eintrag, b) for b in m.get('hart', ()) if not _erfuellt(mn, b)],
            'weich': [eintrag.get('weich_text', {}).get(b, b) for b in m.get('weich', ()) if not _erfuellt(mn, b)],
            'entfaellt': _entfaellt(mn, m) and not _fertig(mn, key),
        })
    laufend = [{'key': i['key'], 'name': eintrag['massnahmen'][i['key']]['name'],
                'icon': eintrag['massnahmen'][i['key']].get('icon', ''), 'status': i['status'], 'fz': i['fz'],
                'call': _call(vehicles, i['fz']), 'platz': i['platz'], 'trupp': i['trupp'],
                'start': i['start'], 'ende': i['ende'], 'ki': i.get('ki', False)}
               for i in _aktiv(mn)]
    warnungen = []
    for w in mn['warnungen']:
        bis = None
        if w['regel'] == 'E1':
            tanks = [mn['tank'][i['fz']] for i in mn['m'] if i['status'] == 'loescht' and i['fz'] in mn['tank']]
            bis = now + min(tanks) if tanks else None
        elif w['regel'] == 'E2' and mn['rate'] > 0:
            bis = now + (eintrag['eskalation']['schwelle'] - mn['brand']) / mn['rate']
        warnungen.append({'text': w['text'], 'bis': bis})
    trend = 'aus' if mn['aus'] else 'steigt' if mn['rate'] > .05 else 'sinkt' if mn['rate'] < -.05 else 'gleich'
    return {
        'stichwort': inc['stichwort'], 'stichwort_start': mn['stichwort_start'],
        'stufe': s, 'stufe_max': mn['stufe_max'], 'ampel': STUFEN[s][0], 'ampel_text': STUFEN[s][1],
        'erkundet': erkundet,
        'variante': eintrag['varianten'][mn['variante']]['name'] if erkundet else None,
        'lage': {
            'brand': round(mn['brand']) if erkundet else None, 'brand_grob': _brand_grob(mn['brand']),
            'trend': trend, 'aus': mn['aus'], 'wasser': mn['wasser'],
            'tank': {vid: round(sec) for vid, sec in mn['tank'].items()},
        },
        'massnahmen': liste,
        'laufend': laufend,
        'fahrzeuge': {v['id']: {'call': v['call'], 'kind': v['kind'], 'faehigkeiten': list(faehigkeiten(v)),
                                'trupps': trupps(v), 'tank_voll': round(tank_voll(v))} for v in da},
        'warnungen': warnungen,
        'nachforderungen': offene_nachforderungen(inc, vehicles),
        'nachgefordert': bool(mn['nachforderungen']),
        'erledigt': sum(1 for e in liste if e['fertig']),
        'pflicht_offen': [e['name'] for e in liste if e['pflicht'] and not e['fertig']],
    }
