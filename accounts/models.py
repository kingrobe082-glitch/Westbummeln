from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models.functions import Lower


class User(AbstractUser):
    """Spielerkonto. Entwickler sind Konten mit is_staff (und is_superuser)."""

    email = models.EmailField('E-Mail-Adresse', unique=True, null=True, blank=True)
    google_sub = models.CharField('Google-ID', max_length=255, unique=True, null=True, blank=True)
    discord_sub = models.CharField('Discord-ID', max_length=32, unique=True, null=True, blank=True)

    class Meta:
        verbose_name = 'Konto'
        verbose_name_plural = 'Konten'
        constraints = [
            models.UniqueConstraint(Lower('username'), name='accounts_user_username_ci_unique'),
        ]

    def save(self, *args, **kwargs):
        # Leere E-Mail als NULL speichern, sonst kollidieren mehrere Konten ohne E-Mail.
        self.email = (self.email or '').strip().lower() or None
        super().save(*args, **kwargs)
