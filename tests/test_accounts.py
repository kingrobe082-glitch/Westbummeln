import secrets

import pytest
from django.contrib.auth import authenticate
from django.db import IntegrityError, transaction

from accounts import services
from accounts.hashers import encode_legacy, legacy_hash

pytestmark = pytest.mark.django_db


def make_legacy_user(django_user_model, name, password, **fields):
    salt = secrets.token_bytes(16)
    user = django_user_model(username=name, **fields)
    user.password = encode_legacy(salt, legacy_hash(password, salt))
    user.save()
    return user


def test_legacy_password_works_and_is_rehashed(django_user_model):
    user = make_legacy_user(django_user_model, 'Alt', 'altespasswort')
    assert user.password.startswith('wb_scrypt$')
    assert authenticate(None, username='alt', password='falsch!!') is None
    assert authenticate(None, username='alt', password='altespasswort') == user
    user.refresh_from_db()
    assert user.password.startswith('scrypt$')
    assert authenticate(None, username='Alt', password='altespasswort') == user


def test_username_is_unique_ignoring_case(django_user_model):
    django_user_model.objects.create(username='Lena')
    with pytest.raises(IntegrityError), transaction.atomic():
        django_user_model.objects.create(username='lena')


def test_users_without_email_do_not_collide(django_user_model):
    django_user_model.objects.create(username='Eins', email='')
    django_user_model.objects.create(username='Zwei')
    assert django_user_model.objects.filter(email__isnull=True).count() == 2


def test_provision_developer(monkeypatch, django_user_model):
    monkeypatch.setenv('DEVELOPER_USERNAME', 'Chef')
    monkeypatch.setenv('DEVELOPER_PASSWORD', 'x' * 16)
    user = services.provision_developer()
    assert user.is_staff and user.is_superuser
    assert services.provision_developer() == user  # zweiter Start ändert nichts


def test_provision_developer_refuses_normal_account(monkeypatch, django_user_model):
    django_user_model.objects.create(username='Chef')
    monkeypatch.setenv('DEVELOPER_USERNAME', 'chef')
    monkeypatch.setenv('DEVELOPER_PASSWORD', 'x' * 16)
    with pytest.raises(RuntimeError, match='gehört bereits einem normalen Konto'):
        services.provision_developer()


def test_test_account_local_and_on_render(monkeypatch, django_user_model):
    monkeypatch.delenv('RENDER', raising=False)
    services.provision_test_account()
    assert authenticate(None, username='test', password='test')
    monkeypatch.setenv('RENDER', 'true')
    monkeypatch.delenv('CREATE_TEST_ACCOUNT', raising=False)
    services.provision_test_account()
    assert not django_user_model.objects.filter(username='test').exists()


def test_real_account_named_test_survives(monkeypatch, django_user_model):
    user = django_user_model(username='test')
    user.set_password('richtigespasswort')
    user.save()
    monkeypatch.setenv('RENDER', 'true')
    services.provision_test_account()
    assert django_user_model.objects.filter(username='test').exists()


def test_google_login(monkeypatch, django_user_model):
    monkeypatch.setattr(services, 'GOOGLE_CLIENT_ID', 'client')
    monkeypatch.setattr(services, 'verify_google', lambda credential: {'sub': 'g-1', 'nonce': 'n1'})
    user = services.login_with_google({'credential': 'token'}, 'n1')
    assert user.username.startswith('Funk-') and not user.has_usable_password()
    assert services.login_with_google({'credential': 'token'}, 'n1') == user
    with pytest.raises(ValueError, match='Google-Anmeldung fehlgeschlagen'):
        services.login_with_google({'credential': 'token'}, 'anderer-nonce')


def test_discord_login_creates_and_reuses_account(django_user_model):
    django_user_model.objects.create(username='Blitz')
    user = services.login_with_discord({'id': '123456789', 'username': 'blitz'})
    assert user.username.startswith('blitz-') and user.discord_sub == '123456789'
    assert services.login_with_discord({'id': '123456789', 'username': 'egal'}) == user
    with pytest.raises(ValueError):
        services.login_with_discord({'id': 'abc'})


def test_admin_user_pages_load(admin_client, django_user_model):
    user = django_user_model.objects.create(username='Spieler')
    assert admin_client.get('/admin/accounts/user/').status_code == 200
    assert admin_client.get(f'/admin/accounts/user/{user.pk}/change/').status_code == 200
    assert admin_client.get('/admin/accounts/user/add/').status_code == 200
