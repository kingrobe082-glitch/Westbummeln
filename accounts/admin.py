"""Konten im Django-Admin, erweitert um die Moderation.

Moderatoren sehen Konten nur (accounts.view_user) und können sperren/entsperren; Admins dürfen
außerdem Kontodaten ändern und Rollen vergeben. Rollenfelder (Gruppen, is_staff, is_superuser,
Einzelrechte) sind im Formular für alle schreibgeschützt: Rollen ändern läuft über „Rolle ändern“,
damit jede Änderung im Moderationsprotokoll landet.
"""
from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin
from django.core.exceptions import PermissionDenied
from django.db.models import Exists, OuterRef, Q
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.template.response import TemplateResponse
from django.urls import path, reverse

from accounts.models import User
from moderation import bans, roles
from moderation.errors import ModerationError
from moderation.forms import BanForm, RoleForm
from moderation.models import Ban

ROLE_FIELDS = ('is_staff', 'is_superuser', 'groups', 'user_permissions')


class BanStatusFilter(admin.SimpleListFilter):
    title = 'Sperre'
    parameter_name = 'sperre'

    def lookups(self, request, model_admin):
        return [('aktiv', 'gesperrt'), ('frei', 'nicht gesperrt'), ('frueher', 'früher gesperrt')]

    def queryset(self, request, queryset):
        active = Exists(Ban.objects.active().filter(user=OuterRef('pk')))
        if self.value() == 'aktiv':
            return queryset.filter(active)
        if self.value() == 'frei':
            return queryset.exclude(active)
        if self.value() == 'frueher':
            return queryset.filter(Exists(Ban.objects.filter(user=OuterRef('pk')))).exclude(active)
        return queryset


class RoleFilter(admin.SimpleListFilter):
    title = 'Rolle'
    parameter_name = 'rolle'

    def lookups(self, request, model_admin):
        return list(roles.ROLES.items())

    def queryset(self, request, queryset):
        admins = Q(is_superuser=True) | Q(groups__name=roles.GROUP_NAMES[roles.ADMIN])
        moderators = Q(groups__name=roles.GROUP_NAMES[roles.MODERATOR])
        if self.value() == roles.ADMIN:
            return queryset.filter(admins).distinct()
        if self.value() == roles.MODERATOR:
            return queryset.filter(moderators).exclude(admins).distinct()
        if self.value() == roles.USER:
            return queryset.exclude(admins).exclude(moderators).distinct()
        return queryset


class BanInline(admin.TabularInline):
    model = Ban
    fk_name = 'user'
    extra = 0
    can_delete = False
    verbose_name_plural = 'Sperrhistorie'
    fields = ('status', 'start', 'end', 'reason', 'created_by', 'lifted', 'lifted_by')
    readonly_fields = fields

    @admin.display(description='Status')
    def status(self, ban):
        if ban.is_active():
            return 'aktiv'
        return 'aufgehoben' if ban.lifted_at else 'abgelaufen'

    @admin.display(description='Beginn')
    def start(self, ban):
        return bans.local_time(ban.starts_at).strftime('%d.%m.%Y, %H:%M')

    @admin.display(description='Ende')
    def end(self, ban):
        return 'dauerhaft' if ban.permanent else bans.local_time(ban.ends_at).strftime('%d.%m.%Y, %H:%M')

    @admin.display(description='aufgehoben am')
    def lifted(self, ban):
        return bans.local_time(ban.lifted_at).strftime('%d.%m.%Y, %H:%M') if ban.lifted_at else '–'

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(User)
class AccountAdmin(UserAdmin):
    change_form_template = 'admin/accounts/user/change_form.html'
    list_display = ('username', 'email', 'role', 'login_method', 'ban_status', 'date_joined', 'last_login')
    list_filter = (BanStatusFilter, RoleFilter, 'is_active')
    search_fields = ('username', 'email', 'google_sub', 'discord_sub')
    list_per_page = 50
    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        ('Persönliche Daten', {'fields': ('first_name', 'last_name', 'email')}),
        ('Moderation', {'fields': ('role', 'login_method', 'ban_status', 'is_active')}),
        ('Rechte', {'classes': ('collapse',), 'fields': ROLE_FIELDS}),
        ('Wichtige Daten', {'fields': ('last_login', 'date_joined')}),
        ('Verknüpfte Anmeldungen', {'fields': ('google_sub', 'discord_sub')}),
    )
    readonly_fields = ('role', 'login_method', 'ban_status', 'last_login', 'date_joined') + ROLE_FIELDS
    inlines = [BanInline]
    actions = ['ban_selected', 'lift_selected']

    # ---------------------------------------------------------------- Spalten

    @admin.display(description='Rolle')
    def role(self, user):
        return roles.ROLES[roles.role_of(user)]

    @admin.display(description='Anmeldung')
    def login_method(self, user):
        methods = []
        if user.has_usable_password():
            methods.append('Passwort')
        if user.google_sub:
            methods.append('Google')
        if user.discord_sub:
            methods.append('Discord')
        return ', '.join(methods) or '–'

    @admin.display(description='Sperre')
    def ban_status(self, user):
        ban = bans.active_ban(user)
        return bans.format_end(ban.ends_at) if ban else '–'

    # ---------------------------------------------------------------- Rechte

    def get_fieldsets(self, request, obj=None):
        fieldsets = super().get_fieldsets(request, obj)
        if obj is not None and not self.has_change_permission(request, obj):
            # Moderatoren sehen weder Passwort-Hash noch den Link „Passwort zurücksetzen“ (wäre 403).
            fieldsets = ((None, {'fields': ('username',)}),) + tuple(fieldsets[1:])
        return fieldsets

    def get_actions(self, request):
        actions = super().get_actions(request)
        if not request.user.has_perm('moderation.ban_user'):
            actions.pop('ban_selected', None)
        if not request.user.has_perm('moderation.lift_ban'):
            actions.pop('lift_selected', None)
        return actions

    def render_change_form(self, request, context, *args, **kwargs):
        context.update(
            can_ban=request.user.has_perm('moderation.ban_user'),
            can_lift=request.user.has_perm('moderation.lift_ban'),
            can_assign_roles=request.user.has_perm('moderation.assign_roles'),
        )
        return super().render_change_form(request, context, *args, **kwargs)

    # ---------------------------------------------------------------- eigene Seiten

    def get_urls(self):
        info = self.opts.app_label, self.opts.model_name
        own = [
            path('<int:user_id>/sperren/', self.admin_site.admin_view(self.ban_view), name='{}_{}_ban'.format(*info)),
            path('<int:user_id>/entsperren/', self.admin_site.admin_view(self.lift_view),
                 name='{}_{}_lift'.format(*info)),
            path('<int:user_id>/rolle/', self.admin_site.admin_view(self.role_view), name='{}_{}_role'.format(*info)),
        ]
        return own + super().get_urls()

    def _change_url(self, user):
        return reverse('admin:accounts_user_change', args=[user.pk])

    def _page(self, request, template, title, **context):
        return TemplateResponse(request, template, {
            **self.admin_site.each_context(request),
            'opts': self.opts,
            'title': title,
            **context,
        })

    def _ban_page(self, request, targets, form, action=None):
        return self._page(request, 'admin/moderation/ban_form.html', 'Konten sperren', targets=targets, form=form,
                          action=action, active={t.pk: bans.active_ban(t) for t in targets})

    def _ban_targets(self, request, targets, form):
        done = 0
        for target in targets:
            try:
                bans.ban_user(request.user, target, form.cleaned_data['reason'], form.cleaned_data['duration'])
                done += 1
            except ModerationError as error:
                self.message_user(request, f'{target.username}: {error}', messages.ERROR)
        if done:
            label = bans.DURATIONS[form.cleaned_data['duration']][0]
            self.message_user(request, f'{done} Konto/Konten gesperrt ({label}). Sitzungen beendet, '
                                       'aus allen Räumen entfernt.', messages.SUCCESS)

    def ban_view(self, request, user_id):
        if not request.user.has_perm('moderation.ban_user'):
            raise PermissionDenied
        target = get_object_or_404(User, pk=user_id)
        form = BanForm(request.POST or None)
        if request.method == 'POST' and form.is_valid():
            self._ban_targets(request, [target], form)
            return HttpResponseRedirect(self._change_url(target))
        return self._ban_page(request, [target], form)

    def lift_view(self, request, user_id):
        if not request.user.has_perm('moderation.lift_ban'):
            raise PermissionDenied
        target = get_object_or_404(User, pk=user_id)
        if request.method == 'POST':
            try:
                bans.lift_ban(request.user, target)
                self.message_user(request, f'Sperre für {target.username} aufgehoben.', messages.SUCCESS)
            except ModerationError as error:
                self.message_user(request, str(error), messages.ERROR)
            return HttpResponseRedirect(self._change_url(target))
        return self._page(request, 'admin/moderation/lift_confirm.html', 'Sperre aufheben', target=target,
                          ban=bans.active_ban(target))

    def role_view(self, request, user_id):
        if not request.user.has_perm('moderation.assign_roles'):
            raise PermissionDenied
        target = get_object_or_404(User, pk=user_id)
        form = RoleForm(request.POST or None, initial={'role': roles.role_of(target)})
        if request.method == 'POST' and form.is_valid():
            try:
                roles.set_role(request.user, target, form.cleaned_data['role'])
                self.message_user(request, f'{target.username} ist jetzt {roles.ROLES[form.cleaned_data["role"]]}.',
                                  messages.SUCCESS)
                return HttpResponseRedirect(self._change_url(target))
            except ModerationError as error:
                self.message_user(request, str(error), messages.ERROR)
        return self._page(request, 'admin/moderation/role_form.html', 'Rolle ändern', target=target, form=form,
                          current=roles.ROLES[roles.role_of(target)])

    # ---------------------------------------------------------------- Aktionen in der Liste

    @admin.action(description='Ausgewählte Konten sperren …')
    def ban_selected(self, request, queryset):
        targets = list(queryset)
        if 'apply' in request.POST:
            form = BanForm(request.POST)
            if form.is_valid():
                self._ban_targets(request, targets, form)
                return None
        else:
            form = BanForm()
        return self._ban_page(request, targets, form, action='ban_selected')

    @admin.action(description='Sperren der ausgewählten Konten aufheben')
    def lift_selected(self, request, queryset):
        done = 0
        for target in queryset:
            try:
                bans.lift_ban(request.user, target)
                done += 1
            except ModerationError as error:
                self.message_user(request, str(error), messages.WARNING)
        if done:
            self.message_user(request, f'{done} Sperre(n) aufgehoben.', messages.SUCCESS)
