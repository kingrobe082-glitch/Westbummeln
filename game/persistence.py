"""Spielräume über einen Neustart retten (Deploy, Absturz, Server-Neustart).

Alle Räume liegen im Speicher des einen gunicorn-Workers (game/rooms.py). Damit ein Deploy laufende
Spiele nicht beendet, schreibt dieser Prozess sie als JSON in eine Datei:

* beim Herunterfahren (gunicorn-Hook `worker_exit` in gunicorn.conf.py, sonst `atexit`),
* zusätzlich alle `SAVE_INTERVAL` Sekunden, aber nur, wenn sich etwas geändert hat (Raum-`rev`),
  damit auch ein Absturz oder SIGKILL höchstens so viel verliert.

Beim Start (einmal pro Prozess, aus westbummeln/wsgi.py; nie in Tests oder manage.py-Befehlen) liest
`start()` die Datei wieder ein. Alle Zeitstempel werden um die Ausfallzeit verschoben: Fahrzeuge
springen nicht ans Ziel, Einsätze machen keinen Fortschrittssprung, und Spieler bekommen `GRACE`
Sekunden, um sich wieder zu melden, bevor sie als offline gelten.

Warum eine Datei und keine Postgres-Tabelle:
* Beim Herunterfahren braucht das Speichern nichts außer dem eigenen Dateisystem. Bei einem Neustart
  des ganzen Hosts stoppt Docker db und web gleichzeitig; eine Datenbank wäre dann oft schon weg.
* tmp-Datei + fsync + os.replace ist atomar: Es liegt immer entweder der alte oder der neue Stand da.
* Die Räume enthalten Spielernamen und Konto-IDs. In einer Tabelle landeten sie in jedem täglichen
  Datenbank-Backup (Aufbewahrung bis 3 Monate). Die Datei wird bei jeder Sicherung überschrieben
  und enthält nur, was ohnehin gerade im Speicher ist.

Eine unbekannte Version oder eine kaputte Datei wird geloggt, nach `<datei>.broken` verschoben,
und der Server startet mit leeren Räumen. Das Laden darf den Start nie verhindern.

NEUE ZEITSTEMPEL-FELDER (Sekunden seit 1970, time.time()) IM RAUM in `TIME_KEYS` eintragen,
sonst überspringen sie nach einem Neustart die Ausfallzeit.
"""
import atexit
import json
import logging
import os
import threading
import time
from collections import deque
from pathlib import Path

from django.conf import settings

from game import aao, engine, rooms
from integrations import discord

log = logging.getLogger(__name__)

VERSION = 1
SAVE_INTERVAL = 30  # Sekunden zwischen zwei Prüfungen, ob sich etwas geändert hat
GRACE = 60  # so lange nach dem Start gilt jeder wiederhergestellte Spieler noch als online

# Schlüssel, deren Zahlenwert ein Zeitpunkt ist – egal, wie tief im Raum sie stehen.
TIME_KEYS = frozenset({
    'last',              # Spieler: letzter Abruf
    'last_seen',         # Raum: letzte Aktion (Löschfrist leerer Räume)
    'ai_last',           # Raum: letzter KI-Einsatz
    'weather_at',        # Raum: letzter Wetterwechsel
    'phase_at',          # Fahrzeug: Beginn der Phase
    'phase_until',       # Fahrzeug: Ankunft
    'unattended_since',  # Fahrzeug: seit wann ohne Spieler
    'updated',           # Einsatz: letzte Fortschrittsberechnung
    'closed_at',         # Einsatz: abgeschlossen um
    'at',                # Raum: Kick-Gedächtnis
})
# Kleinere Zahlen sind keine Zeitpunkte, sondern Startwerte wie ai_last=0 („noch nie“).
EPOCH_MIN = 1_000_000_000

_save_lock = threading.Lock()  # nie zwei Schreibvorgänge gleichzeitig
_started = False
_loaded = False  # erst nach dem Laden speichern, sonst überschriebe ein Fehlstart die Datei
_stopped = False
_last_fingerprint = None


def state_file():
    """Pfad der Zustandsdatei oder None, wenn das Speichern abgeschaltet ist (ROOM_STATE_FILE leer)."""
    path = getattr(settings, 'ROOM_STATE_FILE', '')
    return Path(path) if path else None


# ------------------------------------------------------------------ Umwandeln

def _encode(value):
    if isinstance(value, (deque, tuple, set)):
        return list(value)
    raise TypeError(f'{type(value).__name__} lässt sich nicht speichern')


def _dump_room(r):
    data = dict(r)
    # JSON kennt nur Text-Schlüssel; Konto-IDs sind Zahlen. Deshalb als Liste von Paaren.
    data['banned'] = [[account, name] for account, name in r.get('banned', {}).items()]
    # Anstehende WebRTC-Signale sind nach einem Neustart veraltet; bestehende Sprachverbindungen
    # laufen direkt zwischen den Browsern weiter.
    data['voice_messages'] = []
    data['players'] = {pid: {k: v for k, v in p.items() if k != 'radio_times'}
                       for pid, p in r['players'].items()}
    return data


def _load_room(data):
    data['banned'] = {account: name for account, name in data.get('banned', [])}
    for p in data['players'].values():
        p.pop('radio_times', None)
    # Räume von vor der AAO: alte Stichworte (F1, F2, TH1 …) auf die neuen abbilden.
    for inc in data.get('incidents', []):
        aao.migriere_einsatz(inc)
    return data


def dumps(now=None):
    """Alle Räume als JSON-Text. Nur unter rooms.lock aufrufen."""
    payload = {
        'version': VERSION,
        'saved_at': time.time() if now is None else now,
        'rooms': {code: _dump_room(r) for code, r in rooms.rooms.items()},
        'closed': rooms.closed,
    }
    return json.dumps(payload, default=_encode, ensure_ascii=False, separators=(',', ':'))


def shift_times(value, delta):
    """Alle Zeitpunkte unter TIME_KEYS (rekursiv) um delta Sekunden verschieben."""
    if isinstance(value, dict):
        for key, item in value.items():
            if key in TIME_KEYS and isinstance(item, (int, float)) and not isinstance(item, bool) \
                    and item >= EPOCH_MIN:
                value[key] = item + delta
            else:
                shift_times(item, delta)
    elif isinstance(value, list):
        for item in value:
            shift_times(item, delta)


def parse(text, now):
    """JSON-Text in (Räume, geschlossene Codes) umwandeln, Zeiten an `now` anpassen.

    Wirft ValueError, wenn die Datei nicht passt."""
    payload = json.loads(text)
    if not isinstance(payload, dict) or payload.get('version') != VERSION:
        version = payload.get('version') if isinstance(payload, dict) else None
        raise ValueError(f'unbekannte Version {version!r}')
    saved_at = float(payload['saved_at'])
    # Die Ausfallzeit zählt nicht. Eine Uhr, die rückwärts gesprungen ist, verschiebt nichts nach hinten.
    delta = max(0.0, now - saved_at)
    loaded = {}
    for code, data in payload['rooms'].items():
        if not isinstance(data, dict) or data.get('code') != code:
            raise ValueError(f'Raum {code!r} ist beschädigt')
        room = _load_room(data)
        shift_times(room, delta)
        # Gnadenfrist: Spieler gelten erst GRACE Sekunden nach dem Start als offline.
        for p in room['players'].values():
            p['last'] = max(p['last'], now + GRACE - engine.OFFLINE_TIMEOUT)
        room['rev'] += 1  # Frontends rendern neu
        loaded[code] = room
    closed = {code: at + delta for code, at in payload.get('closed', {}).items()}
    return loaded, closed


# ------------------------------------------------------------------ Datei lesen und schreiben

def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.tmp')
    with open(tmp, 'w', encoding='utf-8') as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def save(force=False, now=None):
    """Räume in die Datei schreiben. Ohne force nur, wenn sich seit dem letzten Speichern etwas geändert hat.

    Liefert True, wenn geschrieben wurde. Wirft nie (Fehler werden geloggt)."""
    global _last_fingerprint
    path = state_file()
    if path is None or not _loaded or _stopped:
        return False
    with _save_lock:
        try:
            with rooms.lock:
                fingerprint = (frozenset((code, r['rev']) for code, r in rooms.rooms.items()),
                               frozenset(rooms.closed))
                if not force and fingerprint == _last_fingerprint:
                    return False
                text = dumps(now)
            _write(path, text)
            _last_fingerprint = fingerprint
            return True
        except Exception:
            log.exception('Räume konnten nicht nach %s gespeichert werden', path)
            return False


def load(now=None):
    """Räume aus der Datei in rooms.rooms übernehmen. Liefert die Zahl der Räume. Wirft nie."""
    global _loaded, _last_fingerprint
    now = time.time() if now is None else now
    path = state_file()
    count = 0
    try:
        if path is not None and path.exists():
            try:
                loaded, closed = parse(path.read_text(encoding='utf-8'), now)
            except Exception as error:
                broken = path.with_name(path.name + '.broken')
                log.error('Gespeicherte Räume in %s unbrauchbar (%s) – starte leer, Datei liegt jetzt unter %s',
                          path, error, broken)
                os.replace(path, broken)
            else:
                # Ein fester Raum bleibt nur, wenn er noch der Discord-Raum ist (DISCORD_ROOM geändert?).
                loaded = {code: r for code, r in loaded.items()
                          if not r.get('permanent') or (discord.ROOM_OK and code == discord.ROOM)}
                with rooms.lock:
                    rooms.rooms.update(loaded)
                    rooms.closed.update(closed)
                    _last_fingerprint = None
                count = len(loaded)
                log.warning('%d Räume aus %s wiederhergestellt', count, path)
    except Exception:
        log.exception('Laden der Räume aus %s fehlgeschlagen – starte leer', path)
    _loaded = True
    return count


def shutdown():
    """Letztes Speichern beim Herunterfahren. Danach speichert der Hintergrund-Thread nicht mehr."""
    global _stopped
    if _stopped or not _loaded:
        return
    if save(force=True):
        log.warning('Räume vor dem Herunterfahren gespeichert')
    _stopped = True


def _loop():
    while not _stopped:
        time.sleep(SAVE_INTERVAL)
        if not _stopped:
            save()


def start():
    """Beim Prozessstart: Räume laden, periodisches Speichern und Speichern beim Beenden einrichten.

    Einmal pro Serverprozess (westbummeln/wsgi.py), vor rooms.start_background."""
    global _started
    if _started:
        return
    _started = True
    if state_file() is None:
        return
    load()
    atexit.register(shutdown)
    threading.Thread(target=_loop, name='raeume-speichern', daemon=True).start()
