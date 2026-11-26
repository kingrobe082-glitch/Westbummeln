"""Admin-Seiten der Moderation: Sperren, Moderationsprotokoll, Django-Änderungsprotokoll, aktive Räume."""
import time

from django.contrib import admin, messages
from django.contrib.admin.models import LogEntry
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseNotAllowed, HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.html import format_html

from game import rooms
from moderation import bans, room_actions
from moderation.errors import ModerationError
from moderation.models import Ban, ModerationEvent, Room

admin.site.site_header = 'Westbummeln – Verwaltung'
admin.site.site_title = 'Westbummeln'
admin.site.index_title = 'Moderation und Konten'


class ReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class BanActiveFilter(admin.SimpleListFilter):
    title = 'Status'
    parameter_name = 'status'

    def lookups(self, request, model_admin):
        return [('aktiv', 'aktiv'), ('beendet', 'abgelaufen oder aufgehoben')]

    def queryset(self, request, queryset):
        active = Ban.objects.active().values('pk')
        if self.value() == 'aktiv':
            return queryset.filter(pk__in=active)
        if self.value() == 'beendet':
            return queryset.exclude(pk__in=active)
        return queryset


@admin.register(Ban)
class BanAdmin(ReadOnlyAdmin):
    list_display = ('user_link', 'status', 'starts_at', 'end', 'reason', 'created_by', 'lifted_by', 'lifted_at')
    list_filter = (BanActiveFilter, ('starts_at', admin.DateFieldListFilter))
    search_fields = ('user__username', 'user__email', 'reason', 'created_by__username')
    list_select_related = ('user', 'created_by', 'lifted_by')
    actions = ['lift_selected']

    @admin.display(description='Konto', ordering='user__username')
    def user_link(self, ban):
        return format_html('<a href="{}">{}</a>', reverse('admin:accounts_user_change', args=[ban.user_id]),
                           ban.user.username)

    @admin.display(description='Status')
    def status(self, ban):
        if ban.is_active():
            return 'aktiv'
        return 'aufgehoben' if ban.lifted_at else 'abgelaufen'

    @admin.display(description='Ende', ordering='ends_at')
    def end(self, ban):
        return 'dauerhaft' if ban.permanent else bans.local_time(ban.ends_at).strftime('%d.%m.%Y, %H:%M')

    def get_actions(self, request):
        actions = super().get_actions(request)
        if not request.user.has_perm('moderation.lift_ban'):
            actions.pop('lift_selected', None)
        return actions

    @admin.action(description='Ausgewählte Sperren aufheben')
    def lift_selected(self, request, queryset):
        for user in {ban.user for ban in queryset.select_related('user')}:
            try:
                bans.lift_ban(request.user, user)
                self.message_user(request, f'Sperre für {user.username} aufgehoben.', messages.SUCCESS)
            except ModerationError as error:
                self.message_user(request, str(error), messages.WARNING)


@admin.register(ModerationEvent)
class ModerationEventAdmin(ReadOnlyAdmin):
    list_display = ('at', 'actor_name', 'action', 'target_name', 'room_code', 'details_text')
    list_filter = ('action', ('at', admin.DateFieldListFilter), 'actor_name')
    search_fields = ('actor_name', 'target_name', 'room_code')
    date_hierarchy = 'at'

    @admin.display(description='Details')
    def details_text(self, event):
        labels = {'duration': 'Dauer', 'reason': 'Grund', 'old': 'vorher', 'new': 'neu', 'player': 'Spieler',
                  'players': 'Spieler im Raum', 'rooms': 'aus Räumen', 'bans': 'Sperren', 'replaced': 'ersetzt',
                  'ends_at': 'Ende'}
        parts = []
        for key, value in event.details.items():
            if value in (None, [], ''):
                continue
            if isinstance(value, list):
                value = ', '.join(str(item) for item in value)
            parts.append(f'{labels.get(key, key)}: {value}')
        return '; '.join(parts)


@admin.register(LogEntry)
class LogEntryAdmin(ReadOnlyAdmin):
    """Djangos eigenes Protokoll der Änderungen im Admin (z. B. Kontodaten bearbeitet)."""
    list_display = ('action_time', 'user', 'content_type', 'object_repr', 'action_flag', 'change_message')
    list_filter = ('action_flag', 'content_type', ('action_time', admin.DateFieldListFilter))
    search_fields = ('object_repr', 'user__username', 'change_message')
    list_select_related = ('user', 'content_type')


@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    """„Aktive Räume“: keine Tabelle, die Seite zeigt game.rooms aus dem Speicher."""

    def has_module_permission(self, request):
        return request.user.has_perm('moderation.view_rooms')

    def has_view_permission(self, request, obj=None):
        return request.user.has_perm('moderation.view_rooms')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_urls(self):
        view = self.admin_site.admin_view
        return [
            path('', view(self.rooms_view), name='moderation_room_changelist'),
            path('entfernen/', view(self.kick_view), name='moderation_room_kick'),
            path('schliessen/', view(self.close_view), name='moderation_room_close'),
        ]

    def rooms_view(self, request):
        if not self.has_view_permission(request):
            raise PermissionDenied
        overview = rooms.overview(time.time())
        return TemplateResponse(request, 'admin/moderation/rooms.html', {
            **self.admin_site.each_context(request),
            'opts': self.opts,
            'title': 'Aktive Räume',
            'rooms': overview,
            'activity': rooms.activity(),
            'can_kick': request.user.has_perm('moderation.kick_player'),
            'can_close': request.user.has_perm('moderation.close_room'),
        })

    def _post_only(self, request):
        if request.method != 'POST':
            return HttpResponseNotAllowed(['POST'])
        return None

    def kick_view(self, request):
        if (response := self._post_only(request)) is not None:
            return response
        code = request.POST.get('room', '')
        try:
            name = room_actions.kick_player(request.user, code, request.POST.get('player', ''))
            self.message_user(request, f'{name} wurde aus Raum {code} entfernt.', messages.SUCCESS)
        except (ModerationError, ValueError) as error:
            self.message_user(request, str(error), messages.ERROR)
        return HttpResponseRedirect(reverse('admin:moderation_room_changelist'))

    def close_view(self, request):
        if (response := self._post_only(request)) is not None:
            return response
        code = request.POST.get('room', '')
        try:
            players = room_actions.close_room(request.user, code)
            self.message_user(request, f'Raum {code} geschlossen ({len(players)} Spieler waren drin).',
                              messages.SUCCESS)
        except (ModerationError, ValueError) as error:
            self.message_user(request, str(error), messages.ERROR)
        return HttpResponseRedirect(reverse('admin:moderation_room_changelist'))
