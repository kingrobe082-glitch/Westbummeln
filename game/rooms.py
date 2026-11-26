"""Raum-Registry: alle Spielräume liegen im Speicher dieses einen Prozesses.

Deshalb läuft gunicorn mit genau 1 Worker (mehrere Threads). Jeder Zugriff auf einen Raum
geschieht unter `lock`.

Räume entstehen nur über `create_room` (Code vom Server) oder als fester Discord-Raum
(`DISCORD_ROOM`). Besitzer eines Raums ist das Konto, das ihn erstellt hat. Das Feld `admin`
im Raum ist die Spieler-ID dieses Kontos, solange es im Raum ist; die Spiellogik prüft
Einstellungen weiterhin über `admin`. Leere Räume werden nach `ROOM_EMPTY_TTL` gelöscht.
"""
import secrets
import threading
import time

from django.conf import settings

from game import engine
from integrations import discord

lock = threading.RLock()
rooms = {}
_started = False

CODE_ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'  # ohne 0/O und 1/I, damit man den Code vorlesen kann
CODE_LENGTH = 6
KICK_MEMORY = 600  # so lange erfährt ein entfernter Spieler beim nächsten Abruf, warum er raus ist

NOT_FOUND = 'Raum nicht gefunden – bitte den Raumcode prüfen.'
SESSION_EXPIRED = 'Sitzung abgelaufen – bitte neu beitreten'
OWNER_ONLY = 'Nur der Raumbesitzer darf das.'
BANNED = 'Du bist für diesen Raum gesperrt.'
KICKED = 'Du wurdest von der Raumverwaltung aus dem Raum entfernt.'
KICKED_BANNED = 'Du wurdest von der Raumverwaltung aus dem Raum entfernt und für diesen Raum gesperrt.'


class KickedError(Exception):
    """Der anfragende Spieler wurde aus dem Raum entfernt."""


# ------------------------------------------------------------------ Räume anlegen und finden

def _add_room(code, owner_account, owner_name, now):
    r = engine.new_room(code)
    r.update(
        owner_account=owner_account,
        owner_name=owner_name,
        permanent=owner_account is None,
        last_seen=now,
        banned={},
        kicked={},
    )
    rooms[code] = r
    return r


def ensure_discord_room(now=None):
    """Den Discord-Raum anlegen, falls `DISCORD_ROOM` gesetzt ist. Er wird nie gelöscht."""
    if discord.ROOM_OK and discord.ROOM not in rooms:
        _add_room(discord.ROOM, None, '', time.time() if now is None else now)


def get_room(code):
    """Liefert einen bestehenden Raum. Nur unter `lock` aufrufen."""
    if code == discord.ROOM:
        ensure_discord_room()
    r = rooms.get(code)
    if r is None:
        raise ValueError(NOT_FOUND)
    return r


def new_code():
    """Zufälligen, noch freien Raumcode erzeugen."""
    while True:
        code = ''.join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))
        if code not in rooms and code != discord.ROOM:
            return code


def owned_rooms(account_id):
    return sum(1 for r in rooms.values() if r['owner_account'] == account_id)


def create_room(account_id, name, is_developer, now):
    """Neuen Raum mit Servercode anlegen und den Ersteller als Besitzer beitreten lassen."""
    limit = settings.ROOM_MAX_PER_ACCOUNT
    if owned_rooms(account_id) >= limit:
        raise ValueError(f'Du verwaltest bereits {limit} Räume. Ein Raum wird 30 Minuten, '
                         'nachdem ihn alle verlassen haben, gelöscht – oder übertrage den Besitz.')
    if len(rooms) >= settings.ROOM_MAX_TOTAL:
        raise ValueError('Zurzeit sind alle Räume belegt. Bitte versuche es später erneut.')
    r = _add_room(new_code(), account_id, name, now)
    result = join(r, account_id, name, is_developer, now)
    result['room'] = r['code']
    result['state'].update(room_info(r, account_id))
    return result


def sweep(now):
    """Räume löschen, in denen seit `ROOM_EMPTY_TTL` Sekunden niemand mehr ist. Nur unter `lock`."""
    # Ein Spieler gilt nach OFFLINE_TIMEOUT Sekunden ohne Abruf als weg; ab dann läuft die Frist.
    limit = engine.OFFLINE_TIMEOUT + settings.ROOM_EMPTY_TTL
    for code, r in list(rooms.items()):
        if r['permanent']:
            continue
        last = max([r['last_seen'], *(p['last'] for p in r['players'].values())])
        if now - last >= limit:
            del rooms[code]


# ------------------------------------------------------------------ Besitzer und Spieler

def sync_admin(r):
    """`admin` (Spieler-ID der Raumverwaltung) aus dem Besitzerkonto ableiten.

    Ohne Besitzer (Discord-Raum) bleibt das bisherige Verhalten: der erste anwesende Spieler."""
    owner = r['owner_account']
    if owner is not None:
        r['admin'] = next((pid for pid, p in r['players'].items() if p['account'] == owner), None)
    elif r['admin'] not in r['players']:
        r['admin'] = next(iter(r['players']), None)


def room_info(r, account_id):
    """Zusätzliche Felder für den Snapshot."""
    info = {'code': r['code'], 'owner_name': r['owner_name'] or None, 'permanent': r['permanent']}
    if r['owner_account'] is not None and account_id == r['owner_account']:
        info['banned'] = [{'account': account, 'name': name} for account, name in r['banned'].items()]
    return info


def join(r, account_id, name, is_developer, now):
    if account_id in r['banned']:
        raise ValueError(BANNED)
    existing = next((p for p in r['players'].values() if p['account'] == account_id), None)
    if existing:
        # Gleiches Konto (neuer Tab, Reload): alte Spieler-ID statt zweitem Eintrag.
        existing['last'] = now
        existing['name'] = name
        return {'id': existing['id'], 'state': engine.snapshot(r)}
    limit = settings.ROOM_MAX_PLAYERS
    if len(r['players']) >= limit:
        raise ValueError(f'Der Raum ist voll (höchstens {limit} Spieler).')
    result = engine.handle(r, {'action': 'join'}, account_id, name, is_developer, now)
    sync_admin(r)
    result['state'] = engine.snapshot(r)
    return result


def _player(r, data, account_id):
    pid = str(data.get('id', ''))
    p = r['players'].get(pid)
    if not p or p['account'] != account_id:
        kicked = r['kicked'].get(pid)
        if kicked and kicked['account'] == account_id:
            raise KickedError(KICKED_BANNED if kicked['banned'] else KICKED)
        raise ValueError(SESSION_EXPIRED)
    return pid, p


def _require_owner(r, p):
    if r['owner_account'] is None or p['account'] != r['owner_account']:
        raise ValueError(OWNER_ONLY)


def _target(r, p, data):
    target = r['players'].get(str(data.get('target', '')))
    if not target:
        raise ValueError('Spieler nicht gefunden')
    if target['account'] == p['account']:
        raise ValueError('Das bist du selbst.')
    return target


def _remove_player(r, target, now):
    """Spieler aus dem Raum nehmen und seine Leitstelle bzw. sein Fahrzeug freigeben.

    Wie engine.clean_offline: ein verlassenes Fahrzeug im Einsatz übernimmt später die KI."""
    tid = target['id']
    freed = []
    if r['dispatcher'] == tid:
        r['dispatcher'] = None
        freed.append('Die Leitstelle')
    vid = target['vehicle']
    if vid and vid in r['vehicles']:
        vehicle = r['vehicles'][vid]
        vehicle['owner'] = None
        vehicle['unattended_since'] = now
        freed.append(vehicle['call'])
    del r['players'][tid]
    r['voice_messages'] = [m for m in r['voice_messages'] if tid not in (m['from'], m['to'])]
    return freed


def _kick(r, pid, p, data, now):
    _require_owner(r, p)
    target = _target(r, p, data)
    ban = data.get('ban') is True
    freed = _remove_player(r, target, now)
    r['kicked'] = {k: v for k, v in r['kicked'].items() if now - v['at'] < KICK_MEMORY}
    r['kicked'][target['id']] = {'account': target['account'], 'at': now, 'banned': ban}
    if ban:
        r['banned'][target['account']] = target['name']
    message = f'{target["name"]} wurde von der Raumverwaltung entfernt'
    message += ' und für diesen Raum gesperrt.' if ban else '.'
    if freed:
        message += ' ' + ' und '.join(freed) + (' sind' if len(freed) > 1 else ' ist') + ' wieder frei.'
    engine.emit(r, 'System', message)


def _transfer_owner(r, pid, p, data, now):
    _require_owner(r, p)
    target = _target(r, p, data)
    limit = settings.ROOM_MAX_PER_ACCOUNT
    if owned_rooms(target['account']) >= limit:
        raise ValueError(f'{target["name"]} verwaltet bereits {limit} Räume.')
    r['owner_account'] = target['account']
    r['owner_name'] = target['name']
    engine.emit(r, 'System', f'{target["name"]} verwaltet jetzt den Raum.')


def _unban(r, pid, p, data, now):
    _require_owner(r, p)
    wanted = str(data.get('account', ''))
    account = next((a for a in r['banned'] if str(a) == wanted), None)
    if account is None:
        raise ValueError('Dieses Konto ist nicht gesperrt.')
    name = r['banned'].pop(account)
    engine.emit(r, 'System', f'Die Sperre für {name} wurde aufgehoben.')


ROOM_ACTIONS = {'kick': _kick, 'transfer_owner': _transfer_owner, 'unban': _unban}


# ------------------------------------------------------------------ Datenschutz (Konto löschen, Export)

def remove_account(account_id, now):
    """Ein gelöschtes Konto aus allen Räumen entfernen.

    Der Spieler verlässt jeden Raum wie bei einem Kick (Leitstelle und Fahrzeug werden frei), Sperr- und
    Kick-Einträge zu dem Konto verschwinden. Besitzt das Konto einen Raum, übernimmt ihn der nächste
    anwesende Spieler; ist niemand mehr da, wird der Raum gelöscht. Der Funkverlauf bleibt (nur Namen,
    flüchtig im Speicher)."""
    with lock:
        for code, r in list(rooms.items()):
            changed = False
            for target in [p for p in r['players'].values() if p['account'] == account_id]:
                freed = _remove_player(r, target, now)
                message = f'{target["name"]} hat das Spiel verlassen.'
                if freed:
                    message += ' ' + ' und '.join(freed) + (' sind' if len(freed) > 1 else ' ist') + ' wieder frei.'
                engine.emit(r, 'System', message)
                changed = True
            r['kicked'] = {pid: k for pid, k in r['kicked'].items() if k['account'] != account_id}
            if r['banned'].pop(account_id, None) is not None:
                changed = True
            if r['owner_account'] == account_id:
                heir = next(iter(r['players'].values()), None)
                if heir is None:
                    del rooms[code]
                    continue
                r['owner_account'] = heir['account']
                r['owner_name'] = heir['name']
                engine.emit(r, 'System', f'{heir["name"]} verwaltet jetzt den Raum.')
                changed = True
            if changed:
                sync_admin(r)
                r['rev'] += 1


def account_rooms(account_id):
    """Was die Räume im Speicher gerade über ein Konto wissen (für den Datenexport)."""
    with lock:
        found = []
        for r in rooms.values():
            player = next((p for p in r['players'].values() if p['account'] == account_id), None)
            owner = r['owner_account'] == account_id
            banned = account_id in r['banned']
            if not (player or owner or banned):
                continue
            entry = {'code': r['code'], 'owner': owner, 'banned': banned, 'player': None}
            if player:
                vehicle = r['vehicles'].get(player['vehicle']) if player['vehicle'] else None
                entry['player'] = {'name': player['name'], 'role': player['role'],
                                   'vehicle': vehicle['call'] if vehicle else None}
            found.append(entry)
        return found


def handle(r, data, account_id, name, is_developer, now):
    """Eine /api-Aktion in einem bestehenden Raum ausführen. Nur unter `lock` aufrufen.

    Der Aufrufer hat engine.clean_offline und engine.update bereits ausgeführt."""
    sync_admin(r)
    action = data.get('action')
    if action == 'join':
        result = join(r, account_id, name, is_developer, now)
    else:
        pid, p = _player(r, data, account_id)
        handler = ROOM_ACTIONS.get(action)
        if handler:
            p['last'] = now
            handler(r, pid, p, data, now)
            r['rev'] += 1
            sync_admin(r)
            result = {'state': engine.snapshot(r)}
        else:
            result = engine.handle(r, data, account_id, name, is_developer, now)
    r['last_seen'] = now
    if 'state' in result:
        result['state'].update(room_info(r, account_id))
    return result


# ------------------------------------------------------------------ Discord, Statistik, Start

def from_discord(name, text):
    """Nachricht aus dem Discord-Kanal als Funkspruch in den Discord-Raum schreiben."""
    with lock:
        r = get_room(discord.ROOM)
        engine.emit(r, name + ' (Discord)', text, kind='discord')
        r['rev'] += 1


def activity():
    """Aktive Räume und Spieler (in den letzten 30 Sekunden gemeldet) für die Entwicklerübersicht."""
    with lock:
        now = time.time()
        active_rooms = active_players = 0
        for current in rooms.values():
            active = sum(now - player['last'] <= engine.OFFLINE_TIMEOUT for player in current['players'].values())
            active_rooms += bool(active)
            active_players += active
        return {'rooms': active_rooms, 'players': active_players, 'rooms_total': len(rooms)}


def start_background():
    """Discord-Raum anlegen, Discord-Spiegelung und Bot-Poller starten. Einmal pro Serverprozess."""
    global _started
    with lock:
        if _started:
            return
        _started = True
        ensure_discord_room()
    engine.radio_hook = discord.post_radio
    discord.start(from_discord)
