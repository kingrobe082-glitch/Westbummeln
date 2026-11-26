"""Sperre nach Fehlversuchen beim Passwort-Login, je Kombination aus Konto und Client-IP.

- Ab 5 Fehlversuchen ist die Kombination gesperrt: zuerst 1 Minute, beim nächsten Mal 5, danach
  jeweils 15 Minuten. Die Zahl der Sperren merkt sich der Server 24 Stunden.
- Ein erfolgreicher Login setzt alles zurück.
- Gesperrt wird nach Konto und IP zusammen: Ein Angreifer sperrt sich selbst aus, aber nie den
  echten Besitzer an dessen eigener IP. Gegen Raten von vielen IPs hilft das IP-Limit nicht;
  dafür bremst es jede einzelne IP (siehe RATE_LIMITS).
- Name, E-Mail und Groß-/Kleinschreibung zählen für dasselbe Konto, sonst ließe sich die Sperre mit
  „FLORIAN“, „florian“, „Florian“ … umgehen. Unbekannte Namen werden genauso gesperrt; so verrät die
  Sperre nicht, ob es ein Konto gibt.

Der Zustand liegt im Django-Cache (LocMem, 1 Worker) und geht bei einem Neustart verloren.
"""
import threading
import time

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db.models import Q

from westbummeln.security import client_ip

FAILURE_LIMIT = 5
LOCK_SECONDS = (60, 5 * 60, 15 * 60)
MEMORY_SECONDS = 24 * 3600
LOCKED_MESSAGE = 'Zu viele Fehlversuche. Bitte warte ein paar Minuten und versuche es dann erneut.'

_lock = threading.Lock()


class LoginLockedError(ValueError):
    """Anmeldung für diese Kombination aus Name und IP vorübergehend gesperrt."""

    def __init__(self):
        super().__init__(LOCKED_MESSAGE)


def account_key(login_name):
    """Gleicher Schlüssel für Name (beliebige Schreibweise) und E-Mail desselben Kontos."""
    key = str(login_name or '').strip()
    users = list(get_user_model().objects.filter(Q(username__iexact=key) | Q(email=key.lower()))[:2])
    # Wie im Login-Backend: Passt der Text auf einen Namen und auf eine fremde E-Mail, gewinnt der Name.
    users.sort(key=lambda user: user.username.lower() != key.lower())
    return f'konto-{users[0].pk}' if users else 'name-' + key.casefold()


def _cache_key(request, login_name):
    return f'wb-lockout:{account_key(login_name)}:{client_ip(request)}'


def _state(key):
    return cache.get(key) or {'failures': 0, 'lockouts': 0, 'until': 0}


def is_locked(request, login_name):
    return _state(_cache_key(request, login_name))['until'] > time.time()


def record_failure(request, login_name):
    key = _cache_key(request, login_name)
    with _lock:
        state = _state(key)
        state['failures'] += 1
        if state['failures'] >= FAILURE_LIMIT:
            state['lockouts'] += 1
            state['failures'] = 0
            seconds = LOCK_SECONDS[min(state['lockouts'], len(LOCK_SECONDS)) - 1]
            state['until'] = time.time() + seconds
        cache.set(key, state, MEMORY_SECONDS)


def reset(request, login_name):
    cache.delete(_cache_key(request, login_name))
