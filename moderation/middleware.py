"""Middleware der Moderation (in settings.MIDDLEWARE nach AuthenticationMiddleware)."""
from zoneinfo import ZoneInfo

from django.conf import settings
from django.contrib.auth import logout
from django.http import HttpResponse
from django.utils import timezone

from moderation.bans import check_not_banned
from moderation.errors import BannedError
from westbummeln.security import over_limit
from westbummeln.views import json_reply

ADMIN_PREFIX = '/admin/'


def ban_guard(get_response):
    """Gesperrte Konten mit noch gültiger Sitzung abmelden.

    Eine Sperre beendet die Sitzungen schon über session_version; dies ist die zweite Sicherung
    (z. B. für eine Sitzung, die genau während des Sperrens entstand). /api und /admin/ antworten mit
    der Sperrmeldung, andere Seiten laufen als abgemeldeter Besucher weiter."""

    def middleware(request):
        user = getattr(request, 'user', None)
        if user is not None and user.is_authenticated:
            try:
                check_not_banned(user)
            except BannedError as error:
                logout(request)
                if request.path == '/api':
                    return json_reply({'error': str(error), 'banned': True}, 403)
                if request.path.startswith(ADMIN_PREFIX):
                    return HttpResponse(str(error), status=403, content_type='text/plain; charset=utf-8')
        return get_response(request)

    return middleware


def admin_guard(get_response):
    """Für /admin/: IP-Limit auf schreibende Anfragen und Uhrzeiten in deutscher Ortszeit."""

    def middleware(request):
        if not request.path.startswith(ADMIN_PREFIX):
            return get_response(request)
        if request.method == 'POST' and over_limit(request, 'moderation'):
            return HttpResponse('Zu viele Anfragen. Bitte warte kurz und versuche es dann erneut.',
                                status=429, content_type='text/plain; charset=utf-8')
        timezone.activate(ZoneInfo(settings.DISPLAY_TIME_ZONE))
        try:
            return get_response(request)
        finally:
            timezone.deactivate()

    return middleware
