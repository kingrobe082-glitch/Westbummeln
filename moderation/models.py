"""Sperren, Moderationsprotokoll und die Rechte für die Raumverwaltung im Admin."""
from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone


class BanQuerySet(models.QuerySet):
    def active(self, now=None):
        """Sperren, die gerade gelten: nicht aufgehoben, begonnen und (dauerhaft oder noch nicht abgelaufen)."""
        now = now or timezone.now()
        return self.filter(lifted_at__isnull=True, starts_at__lte=now).filter(
            Q(ends_at__isnull=True) | Q(ends_at__gt=now))


class Ban(models.Model):
    """Sperre eines Kontos. Ende leer = dauerhaft. Aufgehobene Sperren bleiben als Historie stehen."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='bans',
                             verbose_name='Konto')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='+', verbose_name='gesperrt von')
    reason = models.CharField('Grund', max_length=500)
    starts_at = models.DateTimeField('Beginn', default=timezone.now)
    ends_at = models.DateTimeField('Ende', null=True, blank=True, help_text='Leer = dauerhaft')
    lifted_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                  related_name='+', verbose_name='aufgehoben von')
    lifted_at = models.DateTimeField('aufgehoben am', null=True, blank=True)

    objects = BanQuerySet.as_manager()

    class Meta:
        verbose_name = 'Sperre'
        verbose_name_plural = 'Sperren'
        ordering = ['-starts_at', '-pk']
        default_permissions = ('view',)
        permissions = [('ban_user', 'Konten sperren'), ('lift_ban', 'Sperren aufheben')]

    def __str__(self):
        return f'Sperre für {self.user}'

    @property
    def permanent(self):
        return self.ends_at is None

    def is_active(self, now=None):
        now = now or timezone.now()
        return self.lifted_at is None and self.starts_at <= now and (self.ends_at is None or self.ends_at > now)


class ModerationEvent(models.Model):
    """Protokoll aller Moderationsaktionen. Namen werden mitgespeichert, damit Einträge lesbar bleiben,
    auch wenn ein Konto später gelöscht wird."""

    BAN = 'ban'
    UNBAN = 'unban'
    KICK = 'kick'
    CLOSE_ROOM = 'close_room'
    ROLE = 'role'
    ACTIONS = [
        (BAN, 'Konto gesperrt'),
        (UNBAN, 'Sperre aufgehoben'),
        (KICK, 'Spieler aus Raum entfernt'),
        (CLOSE_ROOM, 'Raum geschlossen'),
        (ROLE, 'Rolle geändert'),
    ]

    at = models.DateTimeField('Zeit', default=timezone.now, db_index=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                              related_name='+', verbose_name='Akteur')
    actor_name = models.CharField('Akteur (Name)', max_length=150)
    action = models.CharField('Aktion', max_length=20, choices=ACTIONS, db_index=True)
    target = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                               related_name='+', verbose_name='Zielkonto')
    target_name = models.CharField('Ziel', max_length=150, blank=True)
    room_code = models.CharField('Raum', max_length=16, blank=True)
    details = models.JSONField('Details', default=dict, blank=True)

    class Meta:
        verbose_name = 'Moderationsprotokoll'
        verbose_name_plural = 'Moderationsprotokoll'
        ordering = ['-at', '-pk']
        default_permissions = ('view',)
        permissions = [('assign_roles', 'Rollen vergeben')]

    def __str__(self):
        return f'{self.get_action_display()} – {self.target_name or self.room_code}'


class Room(models.Model):
    """Keine Tabelle: Die Spielräume liegen im Speicher (game.rooms). Das Modell gibt dem Admin einen
    Eintrag „Aktive Räume“ und trägt die Rechte für Raum-Moderation und Leitstellen-Übernahme."""

    class Meta:
        managed = False
        verbose_name = 'Aktiver Raum'
        verbose_name_plural = 'Aktive Räume'
        default_permissions = ()
        permissions = [
            ('view_rooms', 'Aktive Räume ansehen'),
            ('kick_player', 'Spieler aus Räumen entfernen'),
            ('close_room', 'Räume schließen'),
            ('take_over_dispatch', 'Besetzte Leitstelle übernehmen'),
        ]
