from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.db.models import Q

from accounts import lockout


class UsernameOrEmailBackend(ModelBackend):
    """Anmeldung mit Benutzername (ohne Groß-/Kleinschreibung) oder E-Mail-Adresse.

    Mit request (Spiel-Login, Admin-Login, Passwort ändern) gilt die Sperre nach Fehlversuchen aus
    accounts.lockout. Ist die Kombination gesperrt, wird das Passwort gar nicht erst geprüft und
    request.login_locked gesetzt, damit die View eine eigene Meldung zeigen kann."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None or password is None:
            return None
        if request is not None and lockout.is_locked(request, username):
            request.login_locked = True
            return None
        user = self.check_credentials(username, password)
        if request is not None:
            if user is None:
                lockout.record_failure(request, username)
            else:
                lockout.reset(request, username)
        return user

    def check_credentials(self, username, password):
        key = str(username).strip()
        users = list(
            get_user_model().objects.filter(Q(username__iexact=key) | Q(email=key.lower()))[:2]
        )
        # Passt der Text auf ein Konto als Name und auf ein anderes als E-Mail, gewinnt der Name.
        users.sort(key=lambda user: user.username.lower() != key.lower())
        if not users:
            # Gleiche Rechenzeit wie bei einem vorhandenen Konto, damit man Namen nicht erraten kann.
            get_user_model()().set_password(password)
            return None
        user = users[0]
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
