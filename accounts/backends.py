from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.db.models import Q


class UsernameOrEmailBackend(ModelBackend):
    """Anmeldung mit Benutzername (ohne Groß-/Kleinschreibung) oder E-Mail-Adresse."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None or password is None:
            return None
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
