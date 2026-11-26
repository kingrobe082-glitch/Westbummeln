"""Alte Konten einmalig übernehmen: python manage.py import_legacy_accounts <datei>

<datei> ist entweder die alte accounts.sqlite3 des früheren Servers oder die JSON-Datei aus dem
GitHub-Backup (accounts-backup.json). Der Befehl ist idempotent: Ein zweiter Lauf ändert nichts.

Regeln:
- Ein Konto, das es mit derselben ID und demselben Namen schon gibt, gilt als „schon vorhanden“.
- Kollidiert Name, E-Mail, Google- oder Discord-ID mit einem anderen Konto, wird das alte Konto
  übersprungen und gemeldet (nichts wird überschrieben).
- Sonst wird das Konto mit seiner alten ID angelegt. Ist die ID schon an ein anderes Konto vergeben
  (z. B. das neue Entwicklerkonto), bekommt es eine neue ID.
- Passwörter werden als wb_scrypt übernommen und beim nächsten Login automatisch neu gehasht.
  Konten ohne Passwort (nur Google/Discord) bekommen ein unbrauchbares Passwort.
- Entwickler aus der alten Tabelle developers werden is_staff und is_superuser.
- Das Testkonto test/test wird nie übernommen.
- Danach wird die ID-Folge (Postgres-Sequenz) hinter die höchste ID gesetzt.
"""
import base64
import json
import sqlite3
from pathlib import Path

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import check_password
from django.core.management.base import BaseCommand, CommandError
from django.core.management.color import no_style
from django.db import connection, transaction
from django.db.models import Q

from accounts.hashers import encode_legacy

COLUMNS = ('id', 'name', 'name_key', 'salt', 'password', 'google_sub', 'email', 'discord_sub')
SQLITE_MAGIC = b'SQLite format 3\x00'


MOVE = 'neue ID nötig'


class DryRunError(Exception):
    pass


def read_sqlite(path):
    db = sqlite3.connect(f'file:{Path(path).resolve().as_posix()}?mode=ro', uri=True)
    try:
        present = {row[1] for row in db.execute('PRAGMA table_info(accounts)')}
        if not present:
            raise CommandError('Die SQLite-Datei enthält keine Tabelle accounts.')
        select = ', '.join(c if c in present else f'NULL AS {c}' for c in COLUMNS)
        rows = db.execute(f'SELECT {select} FROM accounts ORDER BY id')
        accounts = [dict(zip(COLUMNS, row, strict=True)) for row in rows]
        has_devs = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='developers'").fetchone()
        developers = {row[0] for row in db.execute('SELECT account FROM developers')} if has_devs else set()
    finally:
        db.close()
    return accounts, developers


def read_backup_json(path):
    try:
        data = json.loads(Path(path).read_text(encoding='utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CommandError(f'Datei ist weder eine SQLite-Datenbank noch gültiges JSON: {error}') from None
    if not isinstance(data, dict) or data.get('version') != 1 or not isinstance(data.get('accounts'), list):
        raise CommandError('Unbekanntes Backup-Format (erwartet version 1 mit einer Liste "accounts").')

    def unb64(value):
        return base64.b64decode(value) if value else None

    accounts = []
    for item in data['accounts']:
        account = {column: item.get(column) for column in COLUMNS}
        account['salt'] = unb64(account['salt'])
        account['password'] = unb64(account['password'])
        accounts.append(account)
    return accounts, set(data.get('developers') or [])


def read_legacy(path):
    path = Path(path)
    if not path.is_file():
        raise CommandError(f'Datei nicht gefunden: {path}')
    with path.open('rb') as handle:
        is_sqlite = handle.read(len(SQLITE_MAGIC)) == SQLITE_MAGIC
    return read_sqlite(path) if is_sqlite else read_backup_json(path)


def legacy_password(account):
    salt, hashed = account['salt'], account['password']
    if salt and hashed:
        return encode_legacy(bytes(salt), bytes(hashed))
    return None


def is_legacy_test_account(account, password):
    return (str(account['name'] or '').lower() == 'test' and password is not None
            and check_password('test', password))


class Command(BaseCommand):
    help = 'Konten aus der alten accounts.sqlite3 oder dem JSON-Backup übernehmen (mehrfach ausführbar).'

    def add_arguments(self, parser):
        parser.add_argument('pfad', help='alte accounts.sqlite3 oder accounts-backup.json')
        parser.add_argument('--probelauf', action='store_true',
                            help='nur anzeigen, was passieren würde, nichts speichern')

    def handle(self, *args, **options):
        accounts, developers = read_legacy(options['pfad'])
        self.counts = {'neu': 0, 'vorhanden': 0, 'übersprungen': 0}
        try:
            with transaction.atomic():
                # Erst alle Konten mit freier alter ID, dann die mit vergebener ID. So nimmt keine
                # neu vergebene ID einem späteren alten Konto seine ID weg.
                moved = [account for account in accounts
                         if self.import_one(account, account['id'] in developers) is MOVE]
                reset_sequence()
                for account in moved:
                    self.import_one(account, account['id'] in developers, new_id=True)
                reset_sequence()
                if options['probelauf']:
                    raise DryRunError
        except DryRunError:
            self.stdout.write('Probelauf: nichts gespeichert.')
        users = get_user_model().objects.count()
        self.stdout.write(self.style.SUCCESS(
            f"Fertig. Neu übernommen: {self.counts['neu']}, schon vorhanden: {self.counts['vorhanden']}, "
            f"übersprungen: {self.counts['übersprungen']}. Konten in der Datenbank: {users}."))

    def skip(self, account, reason):
        self.counts['übersprungen'] += 1
        self.stdout.write(self.style.WARNING(f"Übersprungen: Konto {account['id']} ({account['name']}): {reason}"))

    def import_one(self, account, developer, new_id=False):
        users = get_user_model().objects
        name = str(account['name'] or '').strip()
        email = (account['email'] or '').strip().lower() or None
        google_sub = account['google_sub'] or None
        discord_sub = account['discord_sub'] or None
        password = legacy_password(account)
        if not name:
            return self.skip(account, 'kein Benutzername')
        if is_legacy_test_account(account, password):
            return self.skip(account, 'Testkonto test/test wird nicht übernommen')
        same_id = users.filter(pk=account['id']).first()
        if same_id and same_id.username.lower() == name.lower():
            self.counts['vorhanden'] += 1
            return None
        clash = Q(username__iexact=name)
        for field, value in (('email', email), ('google_sub', google_sub), ('discord_sub', discord_sub)):
            if value:
                clash |= Q(**{field: value})
        if same_id and not new_id:
            return MOVE
        existing = users.filter(clash).first()
        if existing:
            if existing.username.lower() == name.lower() and (
                    (email and existing.email == email) or (google_sub and existing.google_sub == google_sub)
                    or (discord_sub and existing.discord_sub == discord_sub)
                    or (password and existing.password == password)):
                self.counts['vorhanden'] += 1
                return None
            return self.skip(account, f'Name, E-Mail oder Anmelde-ID gehört schon zu Konto {existing.pk} '
                                      f'({existing.username})')
        user = users.model(username=name, email=email, google_sub=google_sub, discord_sub=discord_sub,
                           is_staff=developer, is_superuser=developer)
        if not same_id:
            user.pk = account['id']
        if password:
            user.password = password
        else:
            user.set_unusable_password()
        user.save(force_insert=True)
        self.counts['neu'] += 1
        if same_id:
            self.stdout.write(f"Konto {account['id']} ({name}) hat die neue ID {user.pk} bekommen "
                              f"(alte ID war schon vergeben).")
        return user


def reset_sequence():
    """Postgres: nächste automatische ID hinter die höchste vorhandene setzen. SQLite braucht das nicht."""
    statements = connection.ops.sequence_reset_sql(no_style(), [get_user_model()])
    with connection.cursor() as cursor:
        for sql in statements:
            cursor.execute(sql)
