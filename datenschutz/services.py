"""Konto löschen, Datenexport und das regelmäßige Löschen abgelaufener Sitzungen.

Welche Daten es gibt und wie lange sie bleiben, steht für Spieler in templates/datenschutz.html.
Wer hier etwas ändert (oder dem Konto ein neues Feld gibt), prüft auch diese Seite und den Export.
"""
import threading
import time

from django.contrib.auth import authenticate
from django.contrib.sessions.models import Session
from django.db import transaction
from django.utils import timezone

from accounts.lockout import LoginLockedError
from accounts.services import check_password_input
from game import rooms
from moderation.models import ModerationEvent
from moderation.roles import ROLES, role_of

CLEANUP_INTERVAL = 3600  # Sekunden zwischen zwei Aufräumläufen im laufenden Server
_cleanup_lock = threading.Lock()
_last_cleanup = None


# ------------------------------------------------------------------ Sitzungen

def sessions_of(user_id):
    """Alle noch gültigen Django-Sitzungen eines Kontos.

    Sitzungen haben keinen Fremdschlüssel auf das Konto, die Konto-ID steht nur im verschlüsselten
    Inhalt. Deshalb wird jede gültige Sitzung einmal entschlüsselt; bei einem Spiel dieser Größe
    sind das wenige Hundert Zeilen."""
    key = str(user_id)
    return [session for session in Session.objects.filter(expire_date__gt=timezone.now()).iterator()
            if session.get_decoded().get('_auth_user_id') == key]


def clear_expired_sessions():
    """Abgelaufene Sitzungen löschen (wie `manage.py clearsessions`)."""
    Session.objects.filter(expire_date__lte=timezone.now()).delete()


def cleanup_if_due(now=None):
    """Höchstens einmal pro CLEANUP_INTERVAL aufräumen. Läuft nach Anfragen im Server mit, weil der
    Server keinen eigenen Zeitplaner hat; beim Start räumt zusätzlich entrypoint.sh auf."""
    global _last_cleanup
    now = time.monotonic() if now is None else now
    with _cleanup_lock:
        if _last_cleanup is not None and now - _last_cleanup < CLEANUP_INTERVAL:
            return False
        _last_cleanup = now
    clear_expired_sessions()
    return True


# ------------------------------------------------------------------ Konto löschen

def confirm_deletion(request, data):
    """Prüft die Bestätigung: Passwort bei Passwortkonten, sonst den Benutzernamen.

    Ein falsches Passwort zählt für die Sperre nach Fehlversuchen wie beim Login."""
    user = request.user
    if user.has_usable_password():
        password = data.get('password')
        check_password_input(password)
        if authenticate(request, username=user.username, password=password) is None:
            if getattr(request, 'login_locked', False):
                raise LoginLockedError
            raise ValueError('Das Passwort stimmt nicht. Dein Konto wurde nicht gelöscht.')
        return
    confirm = str(data.get('confirm') or '').strip()
    if confirm.casefold() != user.username.casefold():
        raise ValueError('Bitte gib zur Bestätigung genau deinen Benutzernamen ein. '
                         'Dein Konto wurde nicht gelöscht.')


def delete_account(request, data):
    """Konto nach Bestätigung endgültig löschen: alle Sitzungen, das Konto (mit allem, was per
    Fremdschlüssel daran hängt) und den Spieler in allen Räumen. Abmelden macht die View."""
    confirm_deletion(request, data)
    user = request.user
    account_id = user.pk
    with transaction.atomic():
        Session.objects.filter(session_key__in=[s.session_key for s in sessions_of(account_id)]).delete()
        user.delete()
    rooms.remove_account(account_id, time.time())


# ------------------------------------------------------------------ Datenexport

def _time(value):
    return value.isoformat(timespec='seconds') if value else None


def export_data(request):
    """Alle gespeicherten Daten zum angemeldeten Konto als dict.

    Bewusst eine feste Liste von Feldern statt aller Spalten: Passwort-Hash (enthält das Salt) und
    Sitzungsschlüssel dürfen nie im Export landen, auch nicht, wenn das Modell neue Felder bekommt."""
    user = request.user
    current_key = request.session.session_key
    return {
        'hinweis': 'Alle Daten, die Westbummeln zu deinem Konto gespeichert hat. Dein Passwort ist nur '
                   'als nicht umkehrbarer Hash gespeichert und wird deshalb nicht ausgegeben. '
                   'Erklärungen stehen unter /datenschutz.',
        'erstellt_am': _time(timezone.now()),
        'konto': {
            'id': user.pk,
            'benutzername': user.username,
            'email': user.email,
            'passwort_gesetzt': user.has_usable_password(),
            'google_id': user.google_sub,
            'discord_id': user.discord_sub,
            'registriert_am': _time(user.date_joined),
            'letzte_anmeldung': _time(user.last_login),
            'aktiv': user.is_active,
            'rolle': ROLES[role_of(user)],
        },
        'sperren': [
            {'grund': ban.reason, 'beginn': _time(ban.starts_at), 'ende': _time(ban.ends_at),
             'aufgehoben_am': _time(ban.lifted_at)}
            for ban in user.bans.order_by('starts_at', 'pk')
        ],
        # Einträge im Moderationsprotokoll über dieses Konto. Wer moderiert hat, steht nicht darin:
        # das sind Daten der Moderatorin bzw. des Moderators.
        'moderationsprotokoll': [
            {'zeit': _time(event.at), 'aktion': event.get_action_display(), 'raum': event.room_code or None}
            for event in ModerationEvent.objects.filter(target=user).order_by('at', 'pk')
        ],
        'sitzungen': [
            {'gueltig_bis': _time(session.expire_date), 'dieses_geraet': session.session_key == current_key}
            for session in sessions_of(user.pk)
        ],
        'spielraeume': [
            {
                'raumcode': entry['code'],
                'raumbesitzer': entry['owner'],
                'im_raum_gesperrt': entry['banned'],
                'spieler': entry['player'] and {
                    'name': entry['player']['name'],
                    'rolle': entry['player']['role'],
                    'fahrzeug': entry['player']['vehicle'],
                },
            }
            for entry in rooms.account_rooms(user.pk)
        ],
    }
