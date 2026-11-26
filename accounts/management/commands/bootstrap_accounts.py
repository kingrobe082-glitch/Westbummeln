"""Wird bei jedem Start des Webdienstes nach migrate ausgeführt (siehe entrypoint.sh).

- legt das Entwicklerkonto aus DEVELOPER_USERNAME/DEVELOPER_PASSWORD an,
- legt lokal das Testkonto test/test an bzw. löscht es in Produktion (außer CREATE_TEST_ACCOUNT=1),
- räumt abgelaufene Sitzungen auf.
"""
from django.contrib.sessions.models import Session
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from accounts import services


class Command(BaseCommand):
    help = 'Entwicklerkonto und Testkonto einrichten, abgelaufene Sitzungen löschen.'

    def handle(self, *args, **options):
        try:
            services.provision_developer()
        except RuntimeError as error:
            raise CommandError(str(error)) from None
        services.provision_test_account()
        Session.objects.filter(expire_date__lt=timezone.now()).delete()
