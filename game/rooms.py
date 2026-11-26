"""Raum-Registry: alle Spielräume liegen im Speicher dieses einen Prozesses.

Deshalb läuft gunicorn mit genau 1 Worker (mehrere Threads). Jeder Zugriff auf einen Raum
geschieht unter `lock`.
"""
import threading
import time

from game import engine
from integrations import discord

lock = threading.RLock()
rooms = {}
_started = False


def get_room(code):
    """Liefert den Raum zum Code und legt ihn bei Bedarf an. Nur unter `lock` aufrufen."""
    if code not in rooms:
        rooms[code] = engine.new_room(code)
    return rooms[code]


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
            active = sum(now - player['last'] <= 30 for player in current['players'].values())
            active_rooms += bool(active)
            active_players += active
    return {'rooms': active_rooms, 'players': active_players}


def start_background():
    """Discord-Spiegelung und Bot-Poller starten. Wird einmal pro Serverprozess aufgerufen."""
    global _started
    with lock:
        if _started:
            return
        _started = True
    engine.radio_hook = discord.post_radio
    discord.start(from_discord)
