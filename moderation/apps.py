from django.apps import AppConfig
from django.db.models.signals import post_migrate


class ModerationConfig(AppConfig):
    name = 'moderation'
    verbose_name = 'Moderation'

    def ready(self):
        from django.db.models.signals import post_delete, post_save

        from moderation import bans, roles
        from moderation.models import Ban

        # Nach jedem migrate die Gruppen „Moderator“ und „Admin“ mit ihren Rechten abgleichen.
        post_migrate.connect(roles.ensure_role_groups, sender=self, dispatch_uid='moderation-role-groups')
        # Jede gespeicherte Sperre leert den Sperr-Cache des Kontos, auch wenn sie nicht über
        # moderation.bans angelegt wurde (z. B. in der Shell).
        post_save.connect(bans.forget_ban, sender=Ban, dispatch_uid='moderation-ban-cache')
        post_delete.connect(bans.forget_ban, sender=Ban, dispatch_uid='moderation-ban-cache-delete')
