"""Moderation in Spielräumen: Spieler entfernen, Raum schließen – mit Rechteprüfung und Protokoll."""
import time

from django.contrib.auth import get_user_model

from game import rooms
from moderation import audit
from moderation.errors import ModerationError
from moderation.models import ModerationEvent
from moderation.roles import check_may_moderate


def kick_player(actor, code, player_id):
    if not actor.has_perm('moderation.kick_player'):
        raise ModerationError('Dir fehlt die Berechtigung, Spieler aus Räumen zu entfernen.')
    with rooms.lock:
        r = rooms.rooms.get(code)
        player = r['players'].get(player_id) if r else None
        account_id = player['account'] if player else None
    target = get_user_model().objects.filter(pk=account_id).first() if account_id else None
    if target:
        check_may_moderate(actor, target, 'aus Räumen entfernen')
    removed = rooms.moderation_kick(code, player_id, time.time())
    audit.log(actor, ModerationEvent.KICK, target=target, room_code=code, player=removed['name'])
    return removed['name']


def close_room(actor, code):
    if not actor.has_perm('moderation.close_room'):
        raise ModerationError('Dir fehlt die Berechtigung, Räume zu schließen.')
    players = rooms.close_room(code, time.time())
    audit.log(actor, ModerationEvent.CLOSE_ROOM, room_code=code, players=players)
    return players
