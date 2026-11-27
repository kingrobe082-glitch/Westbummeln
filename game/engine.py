"""Reine Spiellogik der Leitstelle, ohne Django.

Ein Raum ist ein dict (siehe new_room). Alle Funktionen hier erwarten, dass der Aufrufer die
Raumsperre hält (game.rooms.lock). Fehler im Spiel werden als ValueError mit deutscher Meldung
gemeldet; die Meldungen gehen unverändert an das Frontend.

Die Logik stammt aus dem alten server.py; Welle 2C hat Fahrzeiten, Einsatzliste und KI-Übernahme korrigiert.
"""
import json
import random
import re
import secrets
import time
from collections import deque

from game import massnahmen, strassen
from game.parsing import to_int

# Koordinaten beziehen sich auf die vollständige Originalkarte inklusive Legende.
BASE = {1: (.235, .55), 2: (.466, .51), 3: (.565, .215), 4: (.827, .46), 5: (.548, .80), 6: (.276, .15)}
FLEET = [
    {
        'id': f'WB-{unit}-{kind.replace(" ", "")}',
        'call': f'Florian WB {unit} {kind}',
        'unit': unit,
        'kind': kind,
        'seats': 3 if kind == 'KdoW' else 9,
        'base': BASE[unit],
    }
    for unit in range(1, 7)
    for kind in ('HLF 20', 'KdoW', 'LF 20')
]
# Straßenpositionen wurden anhand der vom Spieler gelieferten Karte bestimmt.
PLACES = [
    ('Hauptstraße', .39, .53), ('Marktplatz', .41, .65), ('Schulstraße', .59, .38),
    ('Waldstraße', .28, .19), ('Dorfstraße', .56, .85), ('Nelkenweg', .77, .51),
    ('Mathias-Berg-Straße', .75, .59), ('Robin-Hof-Straße', .77, .69), ('Werkstraße', .86, .86),
    ('Buchenstraße', .92, .52), ('Eichenstraße', .37, .23), ('Bachstraße', .34, .84),
    ('Flurstraße', .69, .26), ('Tannenweg', .87, .32), ('Ahornallee', .91, .39),
    ('Kreuzbergstraße', .82, .20), ('Jägerstraße', .215, .36), ('Scheunenweg', .51, .25),
    ('Blütenstraße', .35, .29), ('Sportplatzring', .32, .39), ('Kirchstraße', .56, .58),
    ('Rosenstraße', .49, .65), ('Sonnenstraße', .55, .68), ('Mozartweg', .91, .69),
    ('Uferstraße', .43, .85), ('Mühlenweg', .29, .87), ('Gartenweg', .32, .94),
    ('Wiesenstraße', .34, .985), ('Bummelbachweg', .51, .93), ('Dorflick', .69, .94),
    ('Bürgerstraße', .63, .92), ('Forstweg', .38, .09), ('Feldweg', .74, .10),
    ('Am Rathauspark', .32, .70), ('Erlenstraße', .92, .60),
]
# Feuerwachen und Gerätehäuser dürfen keine Einsatzorte sein.
STATIONS = [*BASE.values(), (.38, .16), (.90, .37), (.88, .23), (.27, .84), (.92, .84)]
OFFLINE_TIMEOUT = 30
UNATTENDED_DELAY = 20  # Sekunden, bis die KI ein unbesetztes Fahrzeug vor Ort übernimmt
SNAPSHOT_CLOSED = 20  # so viele abgeschlossene Einsätze sieht das Frontend
KEEP_CLOSED = 50  # so viele abgeschlossene Einsätze bleiben im Speicher
WEATHER = ['Sonnig', 'Bewölkt', 'Regen', 'Nebel', 'Windig']
TRAVEL_TIME = {'Sonnig': 12, 'Bewölkt': 13, 'Regen': 17, 'Nebel': 20, 'Windig': 15}
# Fahrten folgen dem Straßennetz (game.strassen). TRAVEL_TIME gilt für eine mittellange Route
# (Mittel über alle Wachen und Einsatzorte); kürzere und längere Routen dauern anteilig kürzer oder
# länger, aber höchstens halb bzw. doppelt so lange, damit das Spiel nicht zäh wird.
ROUTE_REFERENCE = .9
ROUTE_FACTOR = (.5, 2)
WORK_FACTOR = {'Sonnig': 1, 'Bewölkt': 1, 'Regen': .85, 'Nebel': .8, 'Windig': .9}
# KI-Leitstelle (ohne menschliche Leitstelle). Die AI_*-Werte überschreibt westbummeln/settings.py per Env.
# Abstand zwischen zwei Einsätzen: Zufall zwischen MIN und MAX Sekunden, geteilt durch (1 + freie GF-Fahrzeuge).
AI_INCIDENT_MIN_GAP = 20
AI_INCIDENT_MAX_GAP = 60
# Gleichzeitig offene KI-Einsätze: besetzte Fahrzeuge × PER_PLAYER + EXTRA, höchstens AI_MAX_OPEN.
AI_MAX_OPEN_PER_PLAYER = 1
AI_MAX_OPEN_EXTRA = 1
AI_MAX_OPEN = 8
AI_MAX_WAITING = 2  # kein neuer Einsatz, solange so viele noch ganz ohne Fahrzeug warten
AI_SETTINGS = ('AI_INCIDENT_MIN_GAP', 'AI_INCIDENT_MAX_GAP', 'AI_MAX_OPEN_PER_PLAYER', 'AI_MAX_OPEN_EXTRA',
               'AI_MAX_OPEN', 'AI_MAX_WAITING')
AI_REINFORCE_BELOW = 50  # weitere Fahrzeuge alarmiert die KI nur, solange der Einsatz unter 50 % ist
# Stichworte der KI-Leitstelle: (Stichwort, Häufigkeit). Die Fahrzeugzahl ergibt sich aus der Stufe im Stichwort
# (siehe needed_vehicles: F2 = 2, TH1 = 1, BMA = 1).
AI_INCIDENT_TYPES = [
    ('F1 · Kleinbrand', 3), ('F1 · Mülltonnenbrand', 2), ('F1 · PKW-Brand', 2),
    ('F2 · Wohnungsbrand', 2), ('F2 · Kellerbrand', 1), ('F3 · Dachstuhlbrand', 1),
    ('TH1 · Ölspur', 2), ('TH1 · Baum auf Straße', 2), ('TH1 · Türöffnung', 2),
    ('TH1 · Wasser im Keller', 1), ('TH2 · Verkehrsunfall, eingeklemmte Person', 1),
    ('BMA · Brandmeldeanlage', 3), ('ABC1 · Gasgeruch', 1),
]
VOICE_SIGNALS = ('offer', 'answer', 'candidate', 'bye', 'channel')
DISPATCHER_ONLY = 'Nur die besetzte Leitstelle darf diese Aktion ausführen'
UNCHANGED = object()  # Rückgabe einer Aktion, die den Raum nicht verändert hat (rev bleibt gleich)
NACHFORDERUNG_KI_DELAY = 10  # so lange nach einer Nachforderung alarmiert die KI-Leitstelle nach


def _radio_noop(room_code, entry):
    pass


# Wird beim Start auf integrations.discord.post_radio gesetzt (siehe game.rooms).
radio_hook = _radio_noop


def new_room(code, seed=None):
    """Neuer Raum. seed macht den Zufall der KI-Leitstelle reproduzierbar (Tests, Simulation)."""
    return {
        'code': code,
        'players': {},
        'vehicles': {
            v['id']: {**v, 'owner': None, 'status': 2, 'incident': None, 'phase': 'wache', 'phase_at': 0}
            for v in FLEET
        },
        'incidents': [],
        'radio': [],
        'rev': 0,
        'dispatcher': None,
        'ai_last': 0,
        'ai_seq': 0,
        'ai_gap': AI_INCIDENT_MIN_GAP,
        # Nur der Seed liegt im Raum (der Raum muss JSON-speicherbar bleiben, siehe game/persistence.py).
        'ai_seed': secrets.randbits(32) if seed is None else seed,
        'voice_messages': [],
        'voice_seq': 0,
        'admin': None,
        'channels': ['Leitstelle', 'Einsatzstelle', 'Abschnitt 1', 'Abschnitt 2', 'Abschnitt 3'],
        'roles': {'leitstelle': True, 'gf': True},
        'weather_mode': 'auto',
        'weather': 'Sonnig',
        'weather_at': 0,
        'weather_history': [],
    }


def emit(r, author, message, kind='auto', call=None):
    entry = {'time': time.strftime('%H:%M:%S'), 'author': author, 'message': message[:400], 'kind': kind}
    if call:
        entry['call'] = call
    r['radio'].append(entry)
    r['radio'] = r['radio'][-100:]
    if kind != 'discord' and author != 'Wetterdienst':
        radio_hook(r.get('code'), entry)


def default_sections():
    return {'Hauptabschnitt': {'leader': 'KI-Einsatzleitung', 'vehicles': []}}


def new_incident(title, address, pos, creator, now, seed=None):
    inc = {
        'id': secrets.token_hex(4), 'title': title, 'address': address, 'pos': pos, 'creator': creator,
        'created': time.strftime('%H:%M:%S'), 'closed': False, 'assigned': [], 'working': False,
        'progress': 0, 'updated': now, 'sections': default_sections(),
    }
    # Stichworte aus dem Katalog (bisher F1) bekommen Maßnahmen und Lage, alle anderen den Fortschrittsbalken.
    massnahmen.init_einsatz(inc, now, seed)
    return inc


def clean_offline(r, now):
    changed = False
    for pid, p in list(r['players'].items()):
        if now - p['last'] <= OFFLINE_TIMEOUT:
            continue
        if r['dispatcher'] == pid:
            r['dispatcher'] = None
        if r['admin'] == pid:
            r['admin'] = next((other for other in r['players'] if other != pid), None)
        if p['vehicle'] and p['vehicle'] in r['vehicles']:
            vehicle = r['vehicles'][p['vehicle']]
            vehicle['owner'] = None
            vehicle['unattended_since'] = now
        del r['players'][pid]
        r['voice_messages'] = [m for m in r['voice_messages'] if m['from'] != pid and m['to'] != pid]
        emit(r, 'System', f'{p["name"]} wegen Verbindungsverlust entfernt (30 Sekunden offline).')
        changed = True
    if changed:
        r['rev'] += 1


def locate(address):
    a = address.lower()
    for name, x, y in PLACES:
        if name.lower() in a:
            return [x, y]
    raise ValueError('Straße nicht bekannt – bitte einen Ort aus der Karte wählen')


def safe_location(pos):
    return all((pos[0] - x) ** 2 + (pos[1] - y) ** 2 >= .027 ** 2 for x, y in STATIONS)


def is_solo(r):
    return len(r['players']) == 1


def ai_mode(r):
    """Unbesetzte Fahrzeuge dürfen alarmiert werden; eine KI-Besatzung fährt sie."""
    return is_solo(r)


def ai_dispatcher(r):
    """Die KI-Leitstelle läuft, solange kein Spieler die Leitstelle besetzt – auch im Mehrspielerbetrieb."""
    return bool(r['players']) and not r['dispatcher']


def _free(v):
    return v['phase'] == 'wache' and v['status'] != 6 and not v['incident']


def needed_vehicles(inc):
    """Fahrzeugbedarf laut Stichwort: die Stufe (F2 = 2, B3 = 3, TH1 = 1); ohne Stufe (BMA …) 1."""
    match = re.match(r'\s*[^\W\d_]+\s*(\d)', inc['title'])
    return max(1, int(match.group(1))) if match else 1


def ai_crew_block(r, inc):
    """Warum die Leitstelle gerade kein unbesetztes Fahrzeug (KI-Besatzung) alarmieren darf; '' = sie darf.

    Allein im Raum immer erlaubt. Im Mehrspielerbetrieb nur, wenn der Einsatz laut Stichwort mehr
    Fahrzeuge braucht als schon alarmiert sind und kein Spielerfahrzeug mehr frei ist."""
    if ai_mode(r):
        return ''
    if massnahmen.offene_nachforderungen(inc, r['vehicles']):
        return ''  # Nachforderungen dürfen mit KI-Besatzung fahren
    need = needed_vehicles(inc)
    active = sum(1 for vid in inc['assigned'] if vid in r['vehicles']
                 and r['vehicles'][vid]['incident'] == inc['id']
                 and r['vehicles'][vid]['phase'] in ('anfahrt', 'vorort'))
    if active >= need:
        return f'Bedarf gedeckt ({need} Fahrzeug{"e" if need > 1 else ""} laut Stichwort)'
    if any(v['owner'] and _free(v) for v in r['vehicles'].values()):
        return 'erst freie Spielerfahrzeuge alarmieren'
    return ''


def alarm(r, inc, v, now):
    """Fahrzeug zum Einsatz schicken (gemeinsam für Leitstelle und KI)."""
    if v['id'] not in inc['assigned']:
        inc['assigned'].append(v['id'])
    if massnahmen.ist_katalog(inc):
        inc['mn']['zeiten'].setdefault('alarm', now)
    sections = inc.setdefault('sections', default_sections())
    if not any(v['id'] in section['vehicles'] for section in sections.values()):
        sections['Hauptabschnitt']['vehicles'].append(v['id'])
    route = strassen.route(v['base'], inc['pos'])
    _start_trip(v, 'anfahrt', route, trip_duration(r, route), now)
    v.update(status=3, incident=inc['id'])


def trip_duration(r, route):
    """Fahrzeit in Sekunden für eine Route, abhängig vom aktuellen Wetter."""
    factor = strassen.length(route) / ROUTE_REFERENCE
    return travel_time(r) * min(ROUTE_FACTOR[1], max(ROUTE_FACTOR[0], factor))


def _start_trip(v, phase, route, duration, now):
    """Fahrt entlang route beginnen. Weg und Ankunftszeit stehen ab jetzt fest; ein Wetterwechsel ändert sie nicht."""
    v.update(phase=phase, phase_at=now, phase_until=now + duration, phase_from=list(route[0]),
             phase_to=list(route[-1]), phase_route=route)


def _stop(v, phase, pos, now):
    v.update(phase=phase, phase_at=now, phase_until=now, phase_from=list(pos), phase_to=list(pos))
    v.pop('phase_route', None)


def _trip_share(v, now):
    """Zurückgelegter Anteil der laufenden Fahrt (0–1) nach der Zeit."""
    duration = v.get('phase_until', v['phase_at']) - v['phase_at']
    return 1 if duration <= 0 else min(1, max(0, (now - v['phase_at']) / duration))


def vehicle_position(v, now):
    """Position auf der Karte (0–1) zum Zeitpunkt now.

    Entlang phase_route, falls vorhanden; Fahrten aus älteren Räumen ohne Route linear zwischen
    phase_from und phase_to."""
    share = _trip_share(v, now)
    route = v.get('phase_route')
    if route and len(route) > 1:
        return strassen.along(route, share)[0]
    start = v.get('phase_from') or list(v['base'])
    target = v.get('phase_to') or start
    return [start[0] + (target[0] - start[0]) * share, start[1] + (target[1] - start[1]) * share]


def _distance(a, b):
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** .5


def ai_dispatch(r, inc, v, now):
    if not _free(v):
        return False
    alarm(r, inc, v, now)
    emit(r, 'KI-Leitstelle', f'Alarm {v["call"]}: {inc["title"]}, {inc["address"]}.')
    return True


def _crews(r):
    """Fahrzeuge, die ein Spieler als GF besetzt hat (ohne Status 6 – außer Dienst)."""
    vehicles = [r['vehicles'][p['vehicle']] for p in r['players'].values() if p['vehicle'] in r['vehicles']]
    return [v for v in vehicles if v['status'] != 6]


def _ai_vehicle(r, inc):
    """Fahrzeug für die KI-Leitstelle: das nächste freie Spielerfahrzeug.

    Sitzt kein Spieler auf einem Fahrzeug, ein unbesetztes (ohne KdoW), wenn das erlaubt ist."""
    crews = _crews(r)
    if crews:
        return min((v for v in crews if _free(v)), key=lambda v: _distance(v['base'], inc['pos']), default=None)
    if not ai_mode(r):
        return None
    return next((v for v in r['vehicles'].values()
                 if not v['owner'] and _free(v) and v['kind'] != 'KdoW'), None)


def ai_open_limit(r):
    """Höchstzahl gleichzeitig offener Einsätze, die die KI-Leitstelle anlegt."""
    limit = max(1, len(_crews(r))) * AI_MAX_OPEN_PER_PLAYER + AI_MAX_OPEN_EXTRA
    return max(1, min(AI_MAX_OPEN, limit))


def ai_incident_gap(r):
    """Sekunden bis zum nächsten KI-Einsatz: der ausgeloste Abstand, kürzer je mehr GF-Fahrzeuge frei sind."""
    free = sum(1 for v in _crews(r) if _free(v))
    return r.get('ai_gap', AI_INCIDENT_MIN_GAP) / (1 + free)


def _ai_rng(r):
    """Zufall für den nächsten KI-Einsatz, abgeleitet aus Seed und Einsatzzähler des Raums.

    Kein random.Random im Raum ablegen: Räume werden als JSON gespeichert. So bleibt der Ablauf mit
    gleichem Seed reproduzierbar, auch über ein Speichern und Laden hinweg."""
    seed = r.setdefault('ai_seed', secrets.randbits(32))
    return random.Random(f'{seed}:{r["ai_seq"]}')


def _ai_new_incident(r, now):
    rng = _ai_rng(r)
    taken = {tuple(i['pos']) for i in r['incidents'] if not i['closed']}
    locations = [(name, x, y) for name, x, y in PLACES if safe_location((x, y)) and (x, y) not in taken]
    if not locations:
        return False
    name, x, y = rng.choice(locations)
    title, _ = rng.choices(AI_INCIDENT_TYPES, weights=[t[1] for t in AI_INCIDENT_TYPES])[0]
    r['incidents'].append(new_incident(title, name, [x, y], 'KI-Leitstelle', now, seed=f'{r["ai_seed"]}:{r["ai_seq"]}'))
    r['ai_last'] = now
    r['ai_seq'] += 1
    r['ai_gap'] = rng.uniform(AI_INCIDENT_MIN_GAP, AI_INCIDENT_MAX_GAP)
    emit(r, 'KI-Leitstelle', f'Neuer Einsatz: {title} – {name}.')
    return True


def run_ai(r, now):
    # Ohne menschliche Leitstelle übernimmt die KI neue Einsätze und die Alarmierung.
    if not ai_dispatcher(r):
        return False
    changed = False
    open_incidents = [i for i in r['incidents'] if not i['closed']]
    waiting = sum(1 for i in open_incidents if not i['assigned'])
    if (now - r['ai_last'] >= ai_incident_gap(r) and len(open_incidents) < ai_open_limit(r)
            and waiting < AI_MAX_WAITING):
        changed = _ai_new_incident(r, now)
    # Erst bekommt jeder offene Einsatz ein Fahrzeug, dann werden Einsätze bis zur Fahrzeugzahl aufgefüllt.
    open_incidents = [i for i in r['incidents'] if not i['closed']]
    for inc in open_incidents:
        if not inc['assigned']:
            v = _ai_vehicle(r, inc)
            if v and ai_dispatch(r, inc, v, now):
                changed = True
    for inc in open_incidents:
        if massnahmen.ist_katalog(inc) and inc['mn']['nachforderungen']:
            if _ai_nachforderung(r, inc, now):
                changed = True
            continue
        while len(inc['assigned']) < needed_vehicles(inc) and inc['progress'] < AI_REINFORCE_BELOW:
            v = _ai_vehicle(r, inc)
            if not v or not ai_dispatch(r, inc, v, now):
                break
            changed = True
    return changed


def _ai_nachforderung(r, inc, now):
    """KI-Leitstelle erfüllt eine Nachforderung nach NACHFORDERUNG_KI_DELAY Sekunden: passender Typ,
    zuerst Spielerfahrzeuge, sonst mit KI-Besatzung (auch im Mehrspielerbetrieb)."""
    if now - inc['mn'].get('nachgefordert', now) < NACHFORDERUNG_KI_DELAY:
        return False
    changed = False
    for kind in massnahmen.offene_nachforderungen(inc, r['vehicles']):
        free = [v for v in r['vehicles'].values() if v['kind'] == kind and _free(v)]
        free.sort(key=lambda v: (not v['owner'], _distance(v['base'], inc['pos'])))
        if free and ai_dispatch(r, inc, free[0], now):
            changed = True
    return changed


def ai_group_leaders(r, now):
    """KI-Fahrzeugführer starten Maßnahmen, wenn kein menschlicher GF am Fahrzeug sitzt.

    Im KI-Modus sofort. Im Mehrspielermodus erst nach UNATTENDED_DELAY Sekunden ohne Besitzer vor Ort
    (z. B. weil der GF die Verbindung verloren hat), damit der Einsatz nicht ewig offen bleibt."""
    solo = is_solo(r)
    changed = False
    for inc in r['incidents']:
        if inc['closed'] or inc['working'] or massnahmen.ist_katalog(inc):
            continue
        on_site = [r['vehicles'][vid] for vid in inc['assigned']
                   if vid in r['vehicles'] and r['vehicles'][vid]['phase'] == 'vorort'
                   and not r['vehicles'][vid]['owner']]
        if solo and on_site:
            emit(r, 'KI-Gruppenführer', f'{inc["title"]}: Mannschaft beginnt Maßnahmen.')
        else:
            waited = [v for v in on_site
                      if now - max(v['phase_at'], v.get('unattended_since', 0)) >= UNATTENDED_DELAY]
            if not waited:
                continue
            emit(r, 'KI-Gruppenführer', f'KI übernimmt {waited[0]["call"]}: {inc["title"]} – '
                                        'Mannschaft beginnt Maßnahmen.')
        inc['working'] = True
        inc['updated'] = now
        changed = True
    return changed


def travel_time(r):
    return TRAVEL_TIME.get(r['weather'], 12)


def weather_work_factor(r):
    return WORK_FACTOR.get(r['weather'], 1)


def update(r, now=None):
    now = time.time() if now is None else now
    changed = run_ai(r, now)
    if r['weather_mode'] == 'auto' and now - r['weather_at'] > 150:
        r['weather'] = WEATHER[int(now // 150) % len(WEATHER)]
        r['weather_at'] = now
        emit(r, 'Wetterdienst', f'Wetterwechsel: {r["weather"]}.')
        changed = True
    for v in r['vehicles'].values():
        if v['phase'] not in ('anfahrt', 'rueckfahrt'):
            continue
        # Fahrten aus älteren Räumen ohne phase_until enden wie früher nach der aktuellen Fahrzeit.
        if now < v.get('phase_until', v['phase_at'] + travel_time(r)):
            continue
        if v['phase'] == 'anfahrt':
            _stop(v, 'vorort', v.get('phase_to') or v['base'], now)
            v['status'] = 4
            emit(r, v['call'], 'Status 4 – Einsatzstelle erreicht.')
        else:
            _stop(v, 'wache', v['base'], now)
            v.update(status=2, incident=None)
            emit(r, v['call'], 'Status 2 – wieder einsatzbereit auf Wache.')
        changed = True
    if ai_group_leaders(r, now):
        changed = True
    for inc in r['incidents']:
        if inc['closed']:
            continue
        if massnahmen.ist_katalog(inc):
            _progress_katalog(r, inc, now)
            changed = True
        elif inc['working'] and _progress_incident(r, inc, now):
            changed = True
    if changed:
        _prune_incidents(r)
        r['rev'] += 1


def _prune_incidents(r):
    """Alle offenen Einsätze behalten, von den abgeschlossenen nur die zuletzt beendeten."""
    keep = {id(i) for i in _latest_closed(r['incidents'], KEEP_CLOSED)}
    r['incidents'] = [i for i in r['incidents'] if not i['closed'] or id(i) in keep]


def _latest_closed(incidents, count):
    closed = [i for i in incidents if i['closed']]
    closed.sort(key=lambda i: i.get('closed_at', 0))
    return closed[-count:] if count else []


def _progress_incident(r, inc, now):
    changed = False
    active = [r['vehicles'][vid] for vid in inc['assigned']
              if vid in r['vehicles'] and r['vehicles'][vid]['phase'] == 'vorort']
    if active:
        elapsed = now - inc.get('updated', now)
        speed = min(3.5, 1.2 + len(active) * .55) * weather_work_factor(r)
        inc['progress'] = min(100, inc['progress'] + elapsed * speed)
        changed = True
        for section in inc.get('sections', {}).values():
            present = sum(1 for vid in section['vehicles']
                          if vid in r['vehicles'] and r['vehicles'][vid]['phase'] == 'vorort')
            if present:
                section_speed = min(3, 0.8 + present * .55) * weather_work_factor(r)
                section['progress'] = min(100, section.get('progress', 0) + elapsed * section_speed)
    inc['updated'] = now
    if inc['progress'] >= 100:
        _finish_incident(r, inc, now)
        emit(r, 'Leitstelle', f'Einsatz {inc["title"]} abgearbeitet – Rückfahrt eingeleitet.')
        changed = True
    return changed


def _ki_fahrzeuge(r, inc, now):
    """Unbesetzte Fahrzeuge vor Ort, für die der KI-GF Maßnahmen wählt (wie ai_group_leaders)."""
    on_site = [v for v in massnahmen.vor_ort(inc, r['vehicles']) if not v['owner']]
    if is_solo(r):
        return on_site
    waited = [v for v in on_site if now - max(v['phase_at'], v.get('unattended_since', 0)) >= UNATTENDED_DELAY]
    for v in waited:
        if v['id'] not in inc['mn']['ki_fz']:
            inc['mn']['ki_fz'].append(v['id'])
            emit(r, 'KI-Gruppenführer', f'KI übernimmt {v["call"]}: {inc["title"]}.')
    return waited


def _progress_katalog(r, inc, now):
    """Katalog-Einsatz: Lage und Maßnahmen fortschreiben, KI-GF entscheiden lassen, bei Erfolg abschließen."""
    for author, message in massnahmen.tick(inc, r['vehicles'], now, r['weather'], weather_work_factor(r)):
        # Meldungen der Einsatzleitung nennen den Ort, Fahrzeugmeldungen erkennt man am Funkrufnamen.
        emit(r, author, f'{inc["address"]}: {message}' if author == 'Einsatzleitung' else message)
    if not massnahmen.fertig(inc):
        for author, message in massnahmen.ki_waehlen(inc, _ki_fahrzeuge(r, inc, now), now,
                                                     weather_work_factor(r)):
            emit(r, author, message)
        inc['progress'] = massnahmen.fortschritt(inc)
    if massnahmen.fertig(inc):
        _finish_incident(r, inc, now)
        emit(r, 'Leitstelle', f'Einsatz {inc["title"]} abgearbeitet – Rückfahrt eingeleitet.')
        emit(r, 'Leitstelle', massnahmen.bilanz_text(inc))


def _finish_incident(r, inc, now, abgebrochen=False):
    """Einsatz abschließen, Abschnitte leeren und alle noch zugeordneten Fahrzeuge heimschicken.

    Katalog-Einsätze bekommen ihre Einsatzbilanz; der Maßnahmen-Zustand wird danach nicht mehr gebraucht."""
    if massnahmen.ist_katalog(inc):
        inc['bilanz'] = massnahmen.bilanz(inc, now, abgebrochen)
        del inc['mn']
    inc.update(closed=True, progress=100, closed_at=now)
    for section in inc.get('sections', {}).values():
        section['vehicles'] = []
    for vid in inc['assigned']:
        v = r['vehicles'].get(vid)
        if v and v['incident'] == inc['id'] and v['phase'] in ('anfahrt', 'vorort'):
            _send_home(r, v, now)


def _send_home(r, v, now):
    """Rückfahrt ab der aktuellen Position.

    Bricht die Anfahrt ab, fährt das Fahrzeug den bisherigen Weg zurück und braucht dafür anteilig
    so lange, wie es schon unterwegs war. Vom Einsatzort aus geht es über den kürzesten Weg heim."""
    route = v.get('phase_route')
    if v['phase'] == 'anfahrt' and route and len(route) > 1:
        share = _trip_share(v, now)
        _, walked = strassen.along(route, share)
        back = walked[::-1] if len(walked) > 1 else [walked[0], walked[0]]
        duration = trip_duration(r, route) * (strassen.length(walked) / (strassen.length(route) or 1))
    elif v['phase'] == 'anfahrt':
        # Anfahrt aus einem älteren Raum ohne Route: wie früher gerade zurück.
        start = vehicle_position(v, now)
        base = list(v['base'])
        full = _distance(v.get('phase_to') or start, base)
        back = [start, base]
        duration = travel_time(r) * (_distance(start, base) / full if full else 1)
    else:
        back = strassen.route(vehicle_position(v, now), v['base'])
        duration = trip_duration(r, back)
    _start_trip(v, 'rueckfahrt', back, duration, now)
    v['status'] = 1


def _snapshot_incident(r, inc, now):
    if not inc['closed']:
        shown = {key: value for key, value in inc.items() if key != 'mn'}  # Variante erst nach dem Erkunden
        if massnahmen.ist_katalog(inc):
            shown['massnahmen'] = massnahmen.snapshot(inc, r['vehicles'], now)
        return {**shown, 'need': needed_vehicles(inc), 'ai_crew_block': ai_crew_block(r, inc)}
    return {key: value for key, value in inc.items() if key != 'sections'}


def snapshot(r, now=None):
    now = time.time() if now is None else now
    shown = {id(i) for i in _latest_closed(r['incidents'], SNAPSHOT_CLOSED)}
    return {
        'server_time': now,
        'players': [{'id': p['id'], 'name': p['name'], 'vehicle': p['vehicle'], 'role': p['role']}
                    for p in r['players'].values()],
        'vehicles': list(r['vehicles'].values()),
        'incidents': [_snapshot_incident(r, i, now) for i in r['incidents'] if not i['closed'] or id(i) in shown],
        'radio': r['radio'][-100:],
        'rev': r['rev'],
        'dispatcher': r['dispatcher'],
        'ai_mode': ai_mode(r),
        'ai_dispatcher': ai_dispatcher(r),
        'admin': r['admin'],
        'channels': r['channels'],
        'roles': r['roles'],
        'weather': r['weather'],
        'weather_mode': r['weather_mode'],
        'travel_time': travel_time(r),
        'work_factor': weather_work_factor(r),
    }


# ------------------------------------------------------------------ Aktionen

def handle(r, data, account_id, account_name, is_developer, now):
    """Führt eine /api-Aktion aus und liefert die Antwort als dict.

    Der Aufrufer hat clean_offline und update bereits ausgeführt."""
    action = data.get('action')
    if action == 'join':
        return _join(r, account_id, account_name, now)
    pid = str(data.get('id', ''))
    p = r['players'].get(pid)
    if not p or p['account'] != account_id:
        raise ValueError('Sitzung abgelaufen – bitte neu beitreten')
    p['last'] = now
    if action == 'state':
        return {'state': snapshot(r, now)}
    if action == 'settings':
        _settings(r, pid, data, now)
        emit(r, 'System', 'Raumeinstellungen aktualisiert.')
        r['rev'] += 1
        return {'state': snapshot(r, now)}
    if action == 'voice_signal':
        return _voice_signal(r, pid, data)
    if action == 'voice_poll':
        since = max(0, to_int(data.get('since', 0), 'Nachrichtennummer'))
        messages = [m for m in r['voice_messages'] if m['to'] == pid and m['seq'] > since]
        return {'messages': messages, 'seq': r['voice_seq'], 'players': snapshot(r, now)['players']}
    handler = ACTIONS.get(action)
    if handler is None:
        raise ValueError('Unbekannte Aktion')
    if handler(r, pid, p, data, now, is_developer) is not UNCHANGED:
        r['rev'] += 1
    return {'state': snapshot(r, now)}


def _join(r, account_id, name, now):
    pid = secrets.token_urlsafe(18)
    if not r['admin']:
        r['admin'] = pid
    r['players'][pid] = {'id': pid, 'account': account_id, 'name': name, 'vehicle': None, 'role': 'none',
                         'last': now}
    emit(r, 'System', f'{name} ist beigetreten.')
    r['rev'] += 1
    return {'id': pid, 'state': snapshot(r, now)}


def _settings(r, pid, data, now):
    if pid != r['admin']:
        raise ValueError('Nur die Raumverwaltung darf Einstellungen ändern')
    kind = str(data.get('kind', ''))
    if kind == 'vehicle':
        v = r['vehicles'].get(str(data.get('vehicle', '')))
        if not v:
            raise ValueError('Fahrzeug fehlt')
        call = str(data.get('call', '')).strip()[:55]
        seats = to_int(data.get('seats', 9), 'Sitzplätze')
        if not call or not 1 <= seats <= 12:
            raise ValueError('Ungültige Fahrzeugdaten')
        v['call'] = call
        v['seats'] = seats
    elif kind == 'channels':
        channels = data.get('channels')
        if not isinstance(channels, list) or not 1 <= len(channels) <= 8:
            raise ValueError('1–8 Kanäle erforderlich')
        channels = [str(c).strip()[:35] for c in channels]
        if not all(channels) or len(set(channels)) != len(channels):
            raise ValueError('Kanalnamen ungültig')
        r['channels'] = channels
    elif kind == 'roles':
        role = str(data.get('role', ''))
        enabled = data.get('enabled')
        if role not in r['roles'] or not isinstance(enabled, bool):
            raise ValueError('Rolle ungültig')
        r['roles'][role] = enabled
    elif kind == 'weather':
        mode = str(data.get('mode', ''))
        weather = str(data.get('weather', ''))
        if mode not in ('auto', 'manual') or weather not in WEATHER:
            raise ValueError('Wetter ungültig')
        r['weather_mode'] = mode
        r['weather'] = weather
        r['weather_at'] = now
    else:
        raise ValueError('Unbekannte Einstellung')


def _voice_signal(r, pid, data):
    target = str(data.get('to', ''))
    payload = data.get('signal')
    if target not in r['players'] or target == pid:
        raise ValueError('Empfänger nicht online')
    if not isinstance(payload, dict) or payload.get('type') not in VOICE_SIGNALS:
        raise ValueError('Ungültiges Funksignal')
    if len(json.dumps(payload)) > 9000:
        raise ValueError('Signal zu groß')
    r['voice_seq'] += 1
    r['voice_messages'].append({'seq': r['voice_seq'], 'from': pid, 'to': target, 'signal': payload})
    r['voice_messages'] = r['voice_messages'][-350:]
    return {'ok': True}


def _require_dispatcher(r, pid, message=DISPATCHER_ONLY):
    if r['dispatcher'] != pid:
        raise ValueError(message)


def _open_incident(r, data):
    inc = _find_incident(r, data)
    if not inc or inc['closed']:
        raise ValueError('Einsatz nicht verfügbar')
    return inc


def _find_incident(r, data):
    wanted = str(data.get('incident', ''))
    return next((x for x in r['incidents'] if x['id'] == wanted), None)


def _take_ls(r, pid, p, data, now, is_developer):
    if not r['roles']['leitstelle']:
        raise ValueError('Leitstellenrolle gesperrt')
    if p['role'] == 'gf':
        raise ValueError('Bitte zuerst das Fahrzeug verlassen')
    previous_id = r['dispatcher']
    if previous_id == pid:
        return UNCHANGED
    if previous_id:
        if not is_developer or data.get('replace_dispatcher') != previous_id:
            raise ValueError('Leitstelle ist bereits besetzt')
        previous = r['players'][previous_id]
        previous['role'] = 'none'
        message = f'{p["name"]} übernimmt die Leitstelle von {previous["name"]}.'
    else:
        message = f'{p["name"]} übernimmt die Leitstelle.'
    r['dispatcher'] = pid
    p['role'] = 'ls'
    emit(r, 'System', message)


def _leave_ls(r, pid, p, data, now, is_developer):
    if r['dispatcher'] != pid:
        raise ValueError('Du besetzt die Leitstelle nicht')
    r['dispatcher'] = None
    p['role'] = 'none'
    emit(r, 'System', f'{p["name"]} verlässt die Leitstelle.')


def _claim(r, pid, p, data, now, is_developer):
    if not r['roles']['gf']:
        raise ValueError('GF-Rolle gesperrt')
    if p['role'] == 'ls':
        raise ValueError('Leitstelle zuerst verlassen')
    v = r['vehicles'].get(str(data.get('vehicle', '')))
    if not v:
        raise ValueError('Fahrzeug fehlt')
    if v['owner'] and v['owner'] != pid:
        raise ValueError('Fahrzeug ist bereits besetzt')
    if p['vehicle'] and r['vehicles'][p['vehicle']]['phase'] != 'wache':
        raise ValueError('Wechsel nur auf Wache möglich')
    if v['phase'] != 'wache':
        raise ValueError('Fahrzeug ist unterwegs')
    if p['vehicle']:
        r['vehicles'][p['vehicle']]['owner'] = None
    v['owner'] = pid
    p['vehicle'] = v['id']
    p['role'] = 'gf'
    emit(r, 'System', f'{p["name"]} besetzt {v["call"]}.')


def _release(r, pid, p, data, now, is_developer):
    if not p['vehicle']:
        return
    v = r['vehicles'][p['vehicle']]
    if v['phase'] != 'wache':
        raise ValueError('Im Einsatz nicht aussteigen')
    v['owner'] = None
    p['vehicle'] = None
    p['role'] = 'none'
    emit(r, 'System', f'{p["name"]} verlässt {v["call"]}.')


def _status(r, pid, p, data, now, is_developer):
    if p['role'] != 'gf' or not p['vehicle']:
        raise ValueError('Bitte Fahrzeug übernehmen')
    v = r['vehicles'][p['vehicle']]
    status = to_int(data.get('status', 0), 'Status')
    if status not in range(1, 7):
        raise ValueError('Ungültiger Status')
    if v['phase'] != 'wache' and status in (2, 6):
        raise ValueError('Status während Einsatz gesperrt')
    if v['phase'] == 'wache' and status in (3, 4):
        raise ValueError('Status 3/4 erfolgt durch Einsatzfahrt')
    v['status'] = status
    emit(r, v['call'], f'Status {status} – {p["name"]}.')


def _incident(r, pid, p, data, now, is_developer):
    _require_dispatcher(r, pid)
    title = str(data.get('title', '')).strip()[:90]
    address = str(data.get('address', '')).strip()[:120]
    if not title or not address:
        raise ValueError('Stichwort und Einsatzort erforderlich')
    pos = locate(address)
    if not safe_location(pos):
        raise ValueError('An dieser Stelle liegt eine Feuerwache oder ein Gerätehaus – anderen Einsatzort wählen')
    r['incidents'].append(new_incident(title, address, pos, p['name'], now))
    emit(r, 'Leitstelle', f'Neuer Einsatz: {title} – {address}.')


def _dispatch(r, pid, p, data, now, is_developer):
    _require_dispatcher(r, pid)
    inc = _find_incident(r, data)
    v = r['vehicles'].get(str(data.get('vehicle', '')))
    if not inc or inc['closed'] or not v:
        raise ValueError('Einsatz oder Fahrzeug nicht verfügbar')
    if not _free(v):
        raise ValueError('Fahrzeug ist nicht frei')
    if not v['owner'] and (reason := ai_crew_block(r, inc)):
        raise ValueError(f'Unbesetztes Fahrzeug nicht alarmierbar: {reason}')
    alarm(r, inc, v, now)
    emit(r, 'Leitstelle', f'Alarm {v["call"]}: {inc["title"]}, {inc["address"]}.')


def _section_add(r, pid, p, data, now, is_developer):
    _require_dispatcher(r, pid, 'Nur die Leitstelle kann Einsatzabschnitte anlegen')
    inc = _open_incident(r, data)
    name = str(data.get('section', '')).strip()[:35]
    if not name:
        raise ValueError('Abschnittsname fehlt')
    sections = inc.setdefault('sections', default_sections())
    if name in sections or len(sections) >= 6:
        raise ValueError('Abschnitt existiert bereits oder Maximum erreicht')
    sections[name] = {'leader': 'KI-Abschnittsleitung', 'vehicles': [], 'progress': 0}
    emit(r, 'Einsatzleitung', f'{inc["title"]}: Abschnitt {name} eingerichtet.')


def _section_assign(r, pid, p, data, now, is_developer):
    _require_dispatcher(r, pid, 'Nur die Leitstelle kann Fahrzeuge zuweisen')
    inc = _open_incident(r, data)
    vid = str(data.get('vehicle', ''))
    name = str(data.get('section', ''))
    sections = inc.setdefault('sections', default_sections())
    if name not in sections or vid not in inc['assigned']:
        raise ValueError('Abschnitt oder Fahrzeug nicht verfügbar')
    for section in sections.values():
        if vid in section['vehicles']:
            section['vehicles'].remove(vid)
    sections[name]['vehicles'].append(vid)
    emit(r, 'Einsatzleitung', f'{r["vehicles"][vid]["call"]} Abschnitt {name} zugewiesen.')


def _section_leader(r, pid, p, data, now, is_developer):
    _require_dispatcher(r, pid, 'Nur die Leitstelle darf Abschnittsleiter bestimmen')
    inc = _open_incident(r, data)
    sections = inc.setdefault('sections', default_sections())
    name = str(data.get('section', ''))
    leader = str(data.get('leader', ''))
    if name not in sections:
        raise ValueError('Abschnitt nicht vorhanden')
    if leader != 'KI-Abschnittsleitung' and not any(
            player['name'] == leader and player['role'] == 'gf' for player in r['players'].values()):
        raise ValueError('Nur aktive Gruppenführer können Abschnittsleiter sein')
    sections[name]['leader'] = leader
    emit(r, 'Einsatzleitung', f'Abschnitt {name}: Leitung {leader}.')


def _work(r, pid, p, data, now, is_developer):
    if p['role'] != 'gf' or not p['vehicle']:
        raise ValueError('Nur ein GF am Einsatzort kann Maßnahmen starten')
    inc = _open_incident(r, data)
    if p['vehicle'] not in inc['assigned'] or r['vehicles'][p['vehicle']]['phase'] != 'vorort':
        raise ValueError('Zuerst muss ein Fahrzeug die Einsatzstelle erreichen')
    if massnahmen.ist_katalog(inc):
        raise ValueError('Bei diesem Einsatz wählst du die Maßnahmen unter „Meine Einsatzstelle“')
    inc['working'] = True
    inc['updated'] = now
    emit(r, 'Einsatzleitung', f'{inc["title"]}: Maßnahmen eingeleitet.')


def _close(r, pid, p, data, now, is_developer):
    _require_dispatcher(r, pid)
    inc = _find_incident(r, data)
    if not inc:
        raise ValueError('Einsatz nicht gefunden')
    if inc['closed']:
        raise ValueError('Einsatz ist bereits abgeschlossen')
    _finish_incident(r, inc, now, abgebrochen=True)
    _prune_incidents(r)
    emit(r, 'Leitstelle', f'Einsatz {inc["title"]} beendet, Rückfahrt.')
    if inc.get('bilanz'):
        emit(r, 'Leitstelle', massnahmen.bilanz_text(inc))


def _gf_vor_ort(r, p, data):
    """Einsatz und eigenes Fahrzeug für Maßnahmen-Aktionen: nur der GF eines Fahrzeugs vor Ort."""
    if p['role'] != 'gf' or not p['vehicle']:
        raise ValueError('Nur ein GF am Einsatzort kann Maßnahmen starten')
    inc = _open_incident(r, data)
    if not massnahmen.ist_katalog(inc):
        raise ValueError('Für diesen Einsatz gibt es keine Maßnahmenliste')
    v = r['vehicles'][p['vehicle']]
    if v['id'] not in inc['assigned'] or v['incident'] != inc['id'] or v['phase'] != 'vorort':
        raise ValueError('Zuerst muss dein Fahrzeug die Einsatzstelle erreichen')
    return inc, v


def _massnahme(r, pid, p, data, now, is_developer):
    inc, v = _gf_vor_ort(r, p, data)
    emit(r, v['call'], massnahmen.starten(inc, v, str(data.get('key', '')), now, weather_work_factor(r)))


def _massnahme_stop(r, pid, p, data, now, is_developer):
    inc, v = _gf_vor_ort(r, p, data)
    emit(r, v['call'], massnahmen.abbrechen(inc, v, str(data.get('key', ''))))


def _radio(r, pid, p, data, now, is_developer):
    msg = str(data.get('message', '')).strip()[:400]
    if not msg:
        raise ValueError('Funkspruch leer')
    sent = p.setdefault('radio_times', deque())
    while sent and now - sent[0] > 10:
        sent.popleft()
    if len(sent) >= 5:
        raise ValueError('Bitte warte kurz, bevor du den nächsten Funkspruch sendest.')
    sent.append(now)
    vehicle = r['vehicles'].get(p['vehicle']) if p['vehicle'] else None
    emit(r, p['name'], msg, kind='funk', call=vehicle['call'] if vehicle else None)


ACTIONS = {
    'take_ls': _take_ls,
    'leave_ls': _leave_ls,
    'claim': _claim,
    'release': _release,
    'status': _status,
    'incident': _incident,
    'dispatch': _dispatch,
    'section_add': _section_add,
    'section_assign': _section_assign,
    'section_leader': _section_leader,
    'work': _work,
    'massnahme': _massnahme,
    'massnahme_stop': _massnahme_stop,
    'close': _close,
    'radio': _radio,
}
