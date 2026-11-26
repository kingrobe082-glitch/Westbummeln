from moderation.models import ModerationEvent


def log(actor, action, target=None, room_code='', **details):
    """Eintrag ins Moderationsprotokoll."""
    return ModerationEvent.objects.create(
        actor=actor,
        actor_name=actor.username if actor else 'System',
        action=action,
        target=target,
        target_name=target.username if target else '',
        room_code=room_code or '',
        details=details,
    )
