"""Rollen user / moderator / admin über Django-Gruppen.

- admin: Superuser (z. B. das Bootstrap-Konto aus DEVELOPER_USERNAME) oder Gruppe „Admin“.
- moderator: Gruppe „Moderator“.
- user: alle anderen.
Moderatoren und Admins haben is_staff (Zugang zu /admin/). Welche Rechte die Gruppen haben, steht in
GROUP_PERMISSIONS und wird nach jedem migrate abgeglichen.
"""
from django.db import transaction

from moderation import audit
from moderation.errors import ModerationError
from moderation.models import ModerationEvent

USER, MODERATOR, ADMIN = 'user', 'moderator', 'admin'
ROLES = {USER: 'Spieler', MODERATOR: 'Moderator', ADMIN: 'Admin'}
GROUP_NAMES = {MODERATOR: 'Moderator', ADMIN: 'Admin'}

MODERATOR_PERMISSIONS = [
    'accounts.view_user',
    'moderation.view_ban',
    'moderation.ban_user',
    'moderation.lift_ban',
    'moderation.view_moderationevent',
    'moderation.view_rooms',
    'moderation.kick_player',
    'moderation.close_room',
    'moderation.take_over_dispatch',
]
GROUP_PERMISSIONS = {
    MODERATOR: MODERATOR_PERMISSIONS,
    ADMIN: MODERATOR_PERMISSIONS + [
        'accounts.change_user',
        'moderation.assign_roles',
        'admin.view_logentry',
    ],
}


def ensure_role_groups(**kwargs):
    """Gruppen anlegen und ihre Rechte genau auf GROUP_PERMISSIONS setzen (post_migrate)."""
    from django.contrib.auth.models import Group, Permission

    for role, group_name in GROUP_NAMES.items():
        group, _ = Group.objects.get_or_create(name=group_name)
        permissions = []
        for name in GROUP_PERMISSIONS[role]:
            app_label, codename = name.split('.')
            permission = Permission.objects.filter(content_type__app_label=app_label, codename=codename).first()
            if permission:
                permissions.append(permission)
        group.permissions.set(permissions)


def role_of(user):
    if user is None or not user.is_authenticated:
        return USER
    if user.is_superuser:
        return ADMIN
    names = set(user.groups.values_list('name', flat=True))
    if GROUP_NAMES[ADMIN] in names:
        return ADMIN
    if GROUP_NAMES[MODERATOR] in names:
        return MODERATOR
    return USER


def check_may_moderate(actor, target, verb):
    """Niemand sich selbst; Moderatoren nur normale Spieler. `verb` z. B. 'sperren'."""
    if actor.pk == target.pk:
        raise ModerationError(f'Du kannst dich nicht selbst {verb}.')
    if role_of(target) != USER and role_of(actor) != ADMIN:
        raise ModerationError(f'Moderatoren dürfen keine Moderatoren oder Admins {verb}.')


def set_role(actor, target, role):
    """Rolle vergeben (nur Admins). Liefert die bisherige Rolle."""
    from django.contrib.auth.models import Group

    if not actor.has_perm('moderation.assign_roles'):
        raise ModerationError('Nur Admins dürfen Rollen vergeben.')
    if role not in ROLES:
        raise ModerationError('Unbekannte Rolle.')
    if actor.pk == target.pk:
        # Sonst könnte sich der letzte Admin versehentlich selbst entmachten.
        raise ModerationError('Du kannst deine eigene Rolle nicht ändern.')
    old = role_of(target)
    if old == role:
        raise ModerationError(f'{target.username} hat bereits die Rolle {ROLES[role]}.')
    with transaction.atomic():
        groups = [Group.objects.get(name=GROUP_NAMES[role])] if role in GROUP_NAMES else []
        target.groups.set(groups)
        target.is_staff = role != USER
        if role != ADMIN:
            target.is_superuser = False
        target.save(update_fields=['is_staff', 'is_superuser'])
        audit.log(actor, ModerationEvent.ROLE, target=target, old=old, new=role)
    return old
