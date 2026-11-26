"""Kontologik: Registrierung, Anmeldung, Google, Discord, Entwickler- und Testkonto.

Die Prüfungen und deutschen Fehlermeldungen entsprechen dem alten accounts.py.
"""
import os
import re
import secrets
from hmac import compare_digest

from django.conf import settings
from django.contrib.auth import authenticate, get_user_model, update_session_auth_hash
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import F

from accounts.lockout import LoginLockedError

GOOGLE_CLIENT_ID = os.environ.get('GOOGLE_CLIENT_ID', '').strip()
EMAIL_RE = re.compile(r'[^@\s]{1,64}@[^@\s]+\.[^@\s]{2,}')
NAME_RE = re.compile(r'[\w-]{3,24}')
TEST_NAME = 'test'


def check_password_input(password):
    if not isinstance(password, str) or not 1 <= len(password) <= 128:
        raise ValueError('Bitte gib ein Passwort mit höchstens 128 Zeichen ein.')


def check_new_password(password, user):
    """Passwortregeln aus AUTH_PASSWORD_VALIDATORS, Meldungen auf Deutsch."""
    try:
        validate_password(password, user)
    except ValidationError as error:
        raise ValueError(' '.join(error.messages)) from None


def register(data, need_email=False):
    """Neues Passwortkonto. Die E-Mail ist freiwillig (das Formular fragt sie nicht mehr ab, solange es
    keine E-Mail-Bestätigung gibt); wird eine geschickt, muss sie gültig und frei sein."""
    name = str(data.get('name', '')).strip()
    password = data.get('password')
    check_password_input(password)
    if not NAME_RE.fullmatch(name):
        raise ValueError('Benutzername: 3–24 Buchstaben, Zahlen, Unterstriche oder Bindestriche.')
    if len(password) < 8:
        raise ValueError('Das Passwort braucht mindestens 8 Zeichen.')
    email = str(data.get('email') or '').strip().lower()
    if need_email or email:
        if len(email) > 254 or not EMAIL_RE.fullmatch(email):
            raise ValueError('Bitte gib eine gültige E-Mail-Adresse ein.')
    email = email or None
    if email and get_user_model().objects.filter(email=email).exists():
        raise ValueError('Diese E-Mail-Adresse ist bereits registriert.')
    user = get_user_model()(username=name, email=email)
    check_new_password(password, user)
    user.set_password(password)
    try:
        with transaction.atomic():
            if get_user_model().objects.filter(username__iexact=name).exists():
                raise IntegrityError
            user.save()
    except IntegrityError:
        raise ValueError('Dieser Benutzername oder diese E-Mail ist bereits vergeben.') from None
    return user


def login_with_password(request, data):
    name = str(data.get('name', '')).strip()
    password = data.get('password')
    check_password_input(password)
    user = authenticate(request, username=name, password=password)
    if getattr(request, 'login_locked', False):
        raise LoginLockedError
    if user is None:
        raise ValueError('Benutzername oder Passwort stimmt nicht.')
    return user


def change_password(request, data):
    """Neues Passwort setzen. Das alte ist nötig und zählt für die Sperre nach Fehlversuchen.
    Alle anderen Sitzungen enden (der Sitzungs-Hash hängt am Passwort), diese bleibt angemeldet
    und bekommt einen neuen Sitzungsschlüssel."""
    user = request.user
    if not user.has_usable_password():
        raise ValueError('Dieses Konto meldet sich über Google oder Discord an und hat kein Passwort.')
    old = data.get('old_password')
    new = data.get('new_password')
    check_password_input(old)
    check_password_input(new)
    if authenticate(request, username=user.username, password=old) is None:
        if getattr(request, 'login_locked', False):
            raise LoginLockedError
        raise ValueError('Das bisherige Passwort stimmt nicht.')
    check_new_password(new, user)
    user.set_password(new)
    user.save(update_fields=['password'])
    update_session_auth_hash(request, user)
    return user


def logout_everywhere(user):
    """Beendet alle Sitzungen des Kontos auf allen Geräten, auch die aktuelle."""
    get_user_model().objects.filter(pk=user.pk).update(session_version=F('session_version') + 1)


def verify_google(credential):
    """Prüft das Google-ID-Token und liefert die Claims. Ausgelagert, damit Tests es ersetzen können."""
    from google.auth.transport.requests import Request
    from google.oauth2 import id_token

    return id_token.verify_oauth2_token(credential, Request(), GOOGLE_CLIENT_ID)


def login_with_google(data, nonce):
    credential = data.get('credential')
    if not GOOGLE_CLIENT_ID or not nonce or not isinstance(credential, str):
        raise ValueError('Google-Anmeldung ist gerade nicht verfügbar.')
    try:
        claims = verify_google(credential)
        subject = claims['sub']
        token_nonce = claims.get('nonce')
        if not isinstance(token_nonce, str) or not compare_digest(token_nonce, nonce):
            raise ValueError('Nonce ungültig')
    except (ValueError, KeyError):
        raise ValueError('Google-Anmeldung fehlgeschlagen. Bitte lade die Seite neu.') from None
    user = get_user_model().objects.filter(google_sub=subject).first()
    if user:
        return user
    user = get_user_model()(username='Funk-' + secrets.token_hex(4), google_sub=subject)
    user.set_unusable_password()
    try:
        with transaction.atomic():
            user.save()
    except IntegrityError:
        return get_user_model().objects.get(google_sub=subject)
    return user


def login_with_discord(discord_user):
    sub = str(discord_user.get('id') or '')
    if not re.fullmatch(r'\d{5,25}', sub):
        raise ValueError('Discord-Anmeldung fehlgeschlagen.')
    existing = get_user_model().objects.filter(discord_sub=sub).first()
    if existing:
        return existing
    base = re.sub(r'[^\w-]', '', str(discord_user.get('username') or ''))[:20]
    if len(base) < 3:
        base = 'Funk-' + sub[-4:]
    name = base
    for _ in range(20):
        user = get_user_model()(username=name, discord_sub=sub)
        user.set_unusable_password()
        try:
            with transaction.atomic():
                if get_user_model().objects.filter(username__iexact=name).exists():
                    raise IntegrityError
                user.save()
            return user
        except IntegrityError:
            existing = get_user_model().objects.filter(discord_sub=sub).first()
            if existing:
                return existing
            name = base[:19] + '-' + secrets.token_hex(2)
    raise ValueError('Discord-Anmeldung fehlgeschlagen.')


def provision_developer():
    """Legt das Entwicklerkonto aus DEVELOPER_USERNAME/DEVELOPER_PASSWORD an (is_staff + is_superuser)."""
    name = os.environ.get('DEVELOPER_USERNAME', '').strip()
    password = os.environ.get('DEVELOPER_PASSWORD', '')
    if not name and not password:
        return None
    if not NAME_RE.fullmatch(name) or not 16 <= len(password) <= 128:
        raise RuntimeError('DEVELOPER_USERNAME und DEVELOPER_PASSWORD prüfen (Passwort: 16–128 Zeichen).')
    with transaction.atomic():
        user = get_user_model().objects.select_for_update().filter(username__iexact=name).first()
        if not user:
            user = register({'name': name, 'password': password}, need_email=False)
            user.is_staff = user.is_superuser = True
            user.save(update_fields=['is_staff', 'is_superuser'])
        elif not user.is_staff:
            raise RuntimeError('Der Entwicklername gehört bereits einem normalen Konto. Wähle einen anderen Namen.')
    return user


def is_test_account(user):
    """Das Testkonto test/test. Ein echtes Konto namens 'test' hat ein Passwort mit mindestens
    8 Zeichen und passt deshalb nie zum Passwort 'test'."""
    if user is None or user.username.lower() != TEST_NAME or not user.has_usable_password():
        return False
    # check_password ohne setter: ein alter Hash soll beim Prüfen nicht neu gespeichert werden.
    from django.contrib.auth.hashers import check_password
    return check_password(TEST_NAME, user.password)


def remove_test_account():
    user = get_user_model().objects.filter(username__iexact=TEST_NAME).first()
    if not is_test_account(user):
        return False
    user.delete()  # Django-Sitzungen enthalten nur die ID und werden damit ungültig.
    print('Testkonto test/test entfernt.', flush=True)
    return True


def provision_test_account():
    """Lokal: Testkonto test/test anlegen. In Produktion nur mit CREATE_TEST_ACCOUNT=1, sonst wird ein
    vorhandenes Testkonto gelöscht."""
    if settings.PRODUCTION and os.environ.get('CREATE_TEST_ACCOUNT') != '1':
        remove_test_account()
        return
    if get_user_model().objects.filter(username__iexact=TEST_NAME).exists():
        return
    user = get_user_model()(username=TEST_NAME, email='test@example.com')
    user.set_password(TEST_NAME)
    user.save()
