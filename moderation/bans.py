"""Konten sperren und entsperren.

Eine Sperre beendet sofort alle Sitzungen des Kontos (session_version, wie „Überall abmelden“) und
nimmt es aus allen Spielräumen. Anmelden (Passwort, Google, Discord) und /api lehnen gesperrte Konten
mit einer Meldung samt Sperrende ab. Der Sperrstatus je Konto liegt kurz im Cache, damit nicht jede
/api-Anfrage die Datenbank fragt; Sperren und Entsperren leeren den Eintrag sofort.
"""
import time
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from accounts.services import logout_everywhere
from game import rooms
from moderation import audit
from moderation.errors import BannedError, ModerationError
from moderation.models import Ban, ModerationEvent
from moderation.roles import check_may_moderate

DURATIONS = {
    '1h': ('1 Stunde', timedelta(hours=1)),
    '1d': ('1 Tag', timedelta(days=1)),
    '7d': ('7 Tage', timedelta(days=7)),
    'perm': ('dauerhaft', None),
}
REASON_MAX = 500
CACHE_SECONDS = 300
NO_BAN = 'keine'


def local_time(value):
    return timezone.localtime(value, ZoneInfo(settings.DISPLAY_TIME_ZONE))


def format_end(ends_at):
    if ends_at is None:
        return 'dauerhaft'
    return 'bis ' + local_time(ends_at).strftime('%d.%m.%Y, %H:%M Uhr')


def ban_message(ends_at):
    if ends_at is None:
        return 'Dein Konto ist dauerhaft gesperrt.'
    return f'Dein Konto ist gesperrt {format_end(ends_at)}.'


def active_ban(user, now=None):
    """Die am längsten laufende aktive Sperre des Kontos oder None."""
    return (Ban.objects.active(now).filter(user=user)
            .order_by(F('ends_at').desc(nulls_first=True)).first())


def _cache_key(user_id):
    return f'wb-ban:{user_id}'


def _ban_end(user):
    """(gesperrt, Ende) mit Cache. Ende None = dauerhaft."""
    value = cache.get(_cache_key(user.pk))
    if value is None:
        ban = active_ban(user)
        value = NO_BAN if ban is None else (ban.ends_at.timestamp() if ban.ends_at else 'dauerhaft')
        cache.set(_cache_key(user.pk), value, CACHE_SECONDS)
    if value == NO_BAN:
        return False, None
    if value == 'dauerhaft':
        return True, None
    if value <= time.time():  # inzwischen abgelaufen
        return False, None
    return True, datetime.fromtimestamp(value, tz=UTC)


def check_not_banned(user):
    """Wirft BannedError mit deutscher Meldung, wenn das Konto gerade gesperrt ist."""
    banned, ends_at = _ban_end(user)
    if banned:
        raise BannedError(ban_message(ends_at))


def forget(user):
    cache.delete(_cache_key(user.pk))


def forget_ban(sender, instance, **kwargs):
    """Signal-Empfänger: Sperre gespeichert oder gelöscht."""
    cache.delete(_cache_key(instance.user_id))


def ban_user(actor, target, reason, duration):
    """Konto sperren. Eine schon laufende Sperre wird durch die neue ersetzt. Liefert die neue Sperre."""
    if not actor.has_perm('moderation.ban_user'):
        raise ModerationError('Dir fehlt die Berechtigung, Konten zu sperren.')
    reason = str(reason or '').strip()
    if not reason:
        raise ModerationError('Bitte gib einen Grund an.')
    if len(reason) > REASON_MAX:
        raise ModerationError(f'Der Grund darf höchstens {REASON_MAX} Zeichen lang sein.')
    if duration not in DURATIONS:
        raise ModerationError('Bitte wähle eine gültige Dauer.')
    check_may_moderate(actor, target, 'sperren')
    label, length = DURATIONS[duration]
    now = timezone.now()
    with transaction.atomic():
        replaced = list(Ban.objects.active(now).filter(user=target).values_list('pk', flat=True))
        Ban.objects.filter(pk__in=replaced).update(lifted_at=now, lifted_by=actor)
        ban = Ban.objects.create(user=target, created_by=actor, reason=reason, starts_at=now,
                                 ends_at=now + length if length else None)
        logout_everywhere(target)
        event = audit.log(actor, ModerationEvent.BAN, target=target, duration=label, reason=reason,
                          ends_at=ban.ends_at.isoformat() if ban.ends_at else None, replaced=replaced)
    forget(target)
    removed = rooms.remove_banned_account(target.pk, time.time())
    if removed:
        event.details['rooms'] = removed
        event.save(update_fields=['details'])
    return ban


def lift_ban(actor, target):
    """Alle aktiven Sperren des Kontos aufheben. Liefert die Zahl der aufgehobenen Sperren."""
    if not actor.has_perm('moderation.lift_ban'):
        raise ModerationError('Dir fehlt die Berechtigung, Sperren aufzuheben.')
    check_may_moderate(actor, target, 'entsperren')
    now = timezone.now()
    with transaction.atomic():
        active = list(Ban.objects.active(now).filter(user=target).values_list('pk', flat=True))
        if not active:
            raise ModerationError(f'Für {target.username} gibt es keine aktive Sperre.')
        Ban.objects.filter(pk__in=active).update(lifted_at=now, lifted_by=actor)
        audit.log(actor, ModerationEvent.UNBAN, target=target, bans=active)
    forget(target)
    return len(active)
