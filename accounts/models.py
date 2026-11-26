from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models.functions import Lower
from django.utils.crypto import salted_hmac


class User(AbstractUser):
    """Spielerkonto. Entwickler sind Konten mit is_staff (und is_superuser)."""

    email = models.EmailField('E-Mail-Adresse', unique=True, null=True, blank=True)
    google_sub = models.CharField('Google-ID', max_length=255, unique=True, null=True, blank=True)
    discord_sub = models.CharField('Discord-ID', max_length=32, unique=True, null=True, blank=True)
    # Hochzählen meldet das Konto auf allen Geräten ab („Überall abmelden“), siehe _get_session_auth_hash.
    session_version = models.PositiveIntegerField('Sitzungsversion', default=0, editable=False)

    class Meta:
        verbose_name = 'Konto'
        verbose_name_plural = 'Konten'
        constraints = [
            models.UniqueConstraint(Lower('username'), name='accounts_user_username_ci_unique'),
        ]

    def _get_session_auth_hash(self, secret=None):
        """Django prüft bei jeder Anfrage, ob dieser Hash noch zur Sitzung passt. Er hängt vom
        Passwort-Hash ab (Passwort ändern beendet andere Sitzungen) und von session_version.
        Bei Version 0 ist er identisch mit Djangos Standard, bestehende Sitzungen bleiben gültig."""
        if not self.session_version:
            return super()._get_session_auth_hash(secret)
        key_salt = 'westbummeln.accounts.User.get_session_auth_hash'
        value = f'{self.password}:{self.session_version}'
        return salted_hmac(key_salt, value, secret=secret, algorithm='sha256').hexdigest()

    def save(self, *args, **kwargs):
        # Leere E-Mail als NULL speichern, sonst kollidieren mehrere Konten ohne E-Mail.
        self.email = (self.email or '').strip().lower() or None
        super().save(*args, **kwargs)
