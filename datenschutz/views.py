import json

from django.conf import settings
from django.http import HttpResponse
from django.shortcuts import render
from django.views.decorators.cache import never_cache

from accounts import services as account_services
from datenschutz import services
from integrations import discord
from westbummeln.security import ip_limit
from westbummeln.views import json_reply, not_found

EXPORT_FILENAME = 'westbummeln-meine-daten.json'


@never_cache
@ip_limit('export')
def export(request):
    """„Meine Daten herunterladen“: alles zum angemeldeten Konto als JSON-Datei."""
    if request.method != 'GET':
        return not_found(request)
    if not request.user.is_authenticated:
        return json_reply({'error': 'Sitzung abgelaufen – bitte anmelden.'}, 401)
    body = json.dumps(services.export_data(request), ensure_ascii=False, indent=2)
    response = HttpResponse(body, content_type='application/json; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="{EXPORT_FILENAME}"'
    return response


def privacy(request):
    """Datenschutzhinweise. Was gerade eingeschaltet ist (Google, Discord), kommt aus der Konfiguration."""
    if request.method != 'GET':
        return not_found(request)
    context = {
        'session_days': settings.SESSION_COOKIE_AGE // 86400,
        'room_empty_minutes': settings.ROOM_EMPTY_TTL // 60,
        'google_login': bool(account_services.GOOGLE_CLIENT_ID),
        'discord_login': discord.login_enabled(),
        'discord_mirror': discord.WEBHOOK_OK,
        'discord_bot': discord.BOT_OK,
    }
    return render(request, 'datenschutz.html', context)
