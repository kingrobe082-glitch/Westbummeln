"""import_legacy_accounts mit einer echten alten SQLite (vom alten accounts.py erzeugt) und einem JSON-Backup."""
import base64
import importlib.util
import io
import json
import sqlite3
from pathlib import Path

import pytest
from django.contrib.auth import authenticate
from django.core.management import call_command
from django.core.management.base import CommandError

pytestmark = pytest.mark.django_db
LEGACY_CODE = Path(__file__).with_name('legacy_accounts_54c2a9b.py')


def load_legacy_module(db_path, monkeypatch):
    """Lädt den alten accounts.py-Code so, dass er in db_path schreibt."""
    monkeypatch.setenv('ACCOUNT_DB_PATH', str(db_path))
    spec = importlib.util.spec_from_file_location('legacy_accounts', LEGACY_CODE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def legacy_sqlite(tmp_path, monkeypatch):
    """Alte Datenbank wie auf dem früheren Server: Passwortkonten, Discord, Google, Entwickler, Testkonto."""
    path = tmp_path / 'accounts.sqlite3'
    legacy = load_legacy_module(path, monkeypatch)
    with legacy.database() as db:
        legacy.account_for_password(db, {'name': 'Anna', 'email': 'Anna@Example.com', 'password': 'annapass1'},
                                    True)
        legacy.account_for_password(db, {'name': 'Ohne_Mail', 'password': 'ohnemail1'}, True, need_email=False)
        legacy.account_for_discord(db, {'id': '99999999', 'username': 'Discordia'})
        db.execute("INSERT INTO accounts (name, google_sub) VALUES ('Funk-1a2b3c4d', 'google-123')")
    monkeypatch.setenv('DEVELOPER_USERNAME', 'Chefin')
    monkeypatch.setenv('DEVELOPER_PASSWORD', 'entwickler-passwort-16')
    legacy.provision_developer()
    legacy.provision_test_account()
    monkeypatch.delenv('DEVELOPER_USERNAME')
    monkeypatch.delenv('DEVELOPER_PASSWORD')
    return path


def backup_json_from_sqlite(sqlite_path, json_path):
    """Gleiches Format wie backup.export_text() im alten Server."""
    db = sqlite3.connect(sqlite_path)
    rows = db.execute('SELECT id,name,name_key,salt,password,google_sub,email,discord_sub FROM accounts '
                      'ORDER BY id').fetchall()
    devs = [r[0] for r in db.execute('SELECT account FROM developers ORDER BY account')]
    db.close()

    def b64(value):
        return base64.b64encode(value).decode() if value is not None else None

    data = {'version': 1, 'developers': devs, 'accounts': [
        {'id': r[0], 'name': r[1], 'name_key': r[2], 'salt': b64(r[3]), 'password': b64(r[4]),
         'google_sub': r[5], 'email': r[6], 'discord_sub': r[7]} for r in rows]}
    json_path.write_text(json.dumps(data, sort_keys=True, indent=1), encoding='utf-8')
    return json_path


def run_import(path, *args):
    out = io.StringIO()
    call_command('import_legacy_accounts', str(path), *args, stdout=out)
    return out.getvalue()


def check_imported(django_user_model):
    users = {u.username: u for u in django_user_model.objects.all()}
    assert set(users) == {'Anna', 'Ohne_Mail', 'Discordia', 'Funk-1a2b3c4d', 'Chefin'}
    assert [users[n].pk for n in ('Anna', 'Ohne_Mail', 'Discordia', 'Funk-1a2b3c4d', 'Chefin')] == [1, 2, 3, 4, 5]
    assert users['Anna'].email == 'anna@example.com'
    assert users['Ohne_Mail'].email is None
    assert users['Discordia'].discord_sub == '99999999' and not users['Discordia'].has_usable_password()
    assert users['Funk-1a2b3c4d'].google_sub == 'google-123'
    assert users['Chefin'].is_staff and users['Chefin'].is_superuser
    assert not users['Anna'].is_staff

    # Altes Passwort funktioniert (Name und E-Mail) und wird dabei auf den neuen Hasher umgestellt.
    assert users['Anna'].password.startswith('wb_scrypt$')
    assert authenticate(None, username='anna@example.com', password='annapass1') == users['Anna']
    users['Anna'].refresh_from_db()
    assert users['Anna'].password.startswith('scrypt$')
    assert authenticate(None, username='Chefin', password='entwickler-passwort-16')

    # Neue Konten bekommen IDs hinter den übernommenen (Postgres-Sequenz zurückgesetzt).
    new = django_user_model.objects.create(username='Neuling')
    assert new.pk == 6


@pytest.mark.parametrize('source', ['sqlite', 'json'])
def test_import_legacy_accounts(source, legacy_sqlite, tmp_path, django_user_model):
    path = legacy_sqlite if source == 'sqlite' else backup_json_from_sqlite(legacy_sqlite, tmp_path / 'b.json')
    output = run_import(path)
    assert 'Neu übernommen: 5' in output
    assert 'Testkonto test/test wird nicht übernommen' in output
    assert not django_user_model.objects.filter(username='test').exists()

    before = sorted(django_user_model.objects.values_list('id', 'username', 'password', 'is_staff'))
    output = run_import(path)
    assert 'Neu übernommen: 0, schon vorhanden: 5, übersprungen: 1' in output
    assert sorted(django_user_model.objects.values_list('id', 'username', 'password', 'is_staff')) == before

    check_imported(django_user_model)


def test_dry_run_saves_nothing(legacy_sqlite, django_user_model):
    output = run_import(legacy_sqlite, '--probelauf')
    assert 'Probelauf' in output and 'Neu übernommen: 5' in output
    assert django_user_model.objects.count() == 0


def test_old_sqlite_without_email_and_discord_columns(tmp_path, django_user_model):
    path = tmp_path / 'ganz_alt.sqlite3'
    db = sqlite3.connect(path)
    db.execute('CREATE TABLE accounts (id INTEGER PRIMARY KEY, name TEXT NOT NULL, name_key TEXT UNIQUE, '
               'salt BLOB, password BLOB, google_sub TEXT UNIQUE)')
    db.execute("INSERT INTO accounts VALUES (7, 'Uralt', 'uralt', NULL, NULL, 'g-7')")
    db.commit()
    db.close()
    assert 'Neu übernommen: 1' in run_import(path)
    assert django_user_model.objects.get(pk=7).google_sub == 'g-7'


def test_id_taken_by_new_developer_gets_new_id(legacy_sqlite, django_user_model):
    """Startet der neue Server vor dem Import und legt das Entwicklerkonto mit ID 1 an,
    geht kein altes Konto verloren: Anna bekommt eine neue ID, die alte Chefin ist schon da."""
    # ID fest auf 1: Auf Postgres laufen Sequenzen über Tests hinweg weiter.
    django_user_model.objects.create(pk=1, username='Chefin', is_staff=True, is_superuser=True)
    output = run_import(legacy_sqlite)
    assert 'Neu übernommen: 4' in output
    assert 'Konto 5 (Chefin)' in output  # gleicher Name, anderes Konto: übersprungen und gemeldet
    anna = django_user_model.objects.get(username='Anna')
    assert anna.pk == 5  # hinter die höchste übernommene ID (4), Chefin (5) wurde übersprungen
    assert authenticate(None, username='Anna', password='annapass1') == anna
    assert 'Neu übernommen: 0' in run_import(legacy_sqlite)


def test_conflicting_email_is_reported_not_overwritten(legacy_sqlite, django_user_model):
    django_user_model.objects.create(pk=50, username='Andere', email='anna@example.com')
    output = run_import(legacy_sqlite)
    assert 'Übersprungen: Konto 1 (Anna)' in output
    assert django_user_model.objects.get(email='anna@example.com').username == 'Andere'


def test_rejects_unknown_file(tmp_path):
    path = tmp_path / 'kaputt.json'
    path.write_text('{"version": 2}', encoding='utf-8')
    with pytest.raises(CommandError, match='Unbekanntes Backup-Format'):
        run_import(path)
    with pytest.raises(CommandError, match='Datei nicht gefunden'):
        run_import(tmp_path / 'fehlt.sqlite3')
