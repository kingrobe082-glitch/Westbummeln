"""Gemeinsame Hilfen für Tests mit Rollen."""
from django.contrib.auth.models import Group

from moderation.roles import GROUP_NAMES, MODERATOR


def make_moderator(user):
    user.is_staff = True
    user.save(update_fields=['is_staff'])
    user.groups.add(Group.objects.get(name=GROUP_NAMES[MODERATOR]))
    return user
