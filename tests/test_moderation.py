"""Moderation: Rollen, Sperren, Admin-Seiten, Raum-Moderation und Protokoll."""
from datetime import timedelta

import pytest
from django.contrib.auth.models import Group
from django.test import Client
from django.utils import timezone

from accounts import services
from game import rooms
from integrations import discord
from moderation import bans, roles
from moderation.errors import ModerationError
from moderation.models import Ban, ModerationEvent
from tests.conftest import GameClient
from tests.helpers import make_moderator

pytestmark = pytest.mark.django_db
PASSWORD = 'Funkgeraet-42'


# ------------------------------------------------------------------ Hilfen

def register(name):
    client = GameClient()
    response = client.account('register', name=name, email=f'{name.lower()}@example.com', password=PASSWORD)
    assert response.status_code == 200, response.json()
    return client


def make_admin(user):
    user.is_staff = True
    user.save(update_fields=['is_staff'])
    user.groups.add(Group.objects.get(name=roles.GROUP_NAMES[roles.ADMIN]))
    return user


def admin_client(user):
    """Django-Testclient mit Admin-Sitzung; CSRF wird wie im Browser geprüft."""
    client = Client(enforce_csrf_checks=True)
    client.force_login(user)
    client.get('/admin/')
    return client


def admin_post(client, path, data):
    return client.post(path, {**data, 'csrfmiddlewaretoken': client.cookies['csrftoken'].value})


@pytest.fixture
def people(django_user_model):
    """Spieler, Moderator und Admin, jeweils mit Spiel-Client."""
    clients = {name: register(name) for name in ('Spieler', 'Moderator', 'Chefin', 'Zweiter')}
    users = {name: django_user_model.objects.get(username=name) for name in clients}
    make_moderator(users['Moderator'])
    make_admin(users['Chefin'])
    return clients, users


# ------------------------------------------------------------------ Rollen

def test_role_groups_exist_with_permissions():
    moderator = Group.objects.get(name='Moderator')
    admin = Group.objects.get(name='Admin')
    mod_perms = {f'{p.content_type.app_label}.{p.codename}' for p in moderator.permissions.all()}
    admin_perms = {f'{p.content_type.app_label}.{p.codename}' for p in admin.permissions.all()}
    assert mod_perms == set(roles.GROUP_PERMISSIONS['moderator'])
    assert admin_perms == set(roles.GROUP_PERMISSIONS['admin'])
    assert 'moderation.assign_roles' not in mod_perms


def test_role_of(people, django_user_model):
    _, users = people
    assert roles.role_of(users['Spieler']) == 'user'
    assert roles.role_of(users['Moderator']) == 'moderator'
    assert roles.role_of(users['Chefin']) == 'admin'
    superuser = django_user_model.objects.create(username='Super', is_superuser=True, is_staff=True)
    assert roles.role_of(superuser) == 'admin'


def test_bootstrap_developer_becomes_admin(monkeypatch):
    monkeypatch.setenv('DEVELOPER_USERNAME', 'Gruender')
    monkeypatch.setenv('DEVELOPER_PASSWORD', 'x' * 16)
    user = services.provision_developer()
    assert roles.role_of(user) == 'admin'
    assert user.has_perm('moderation.ban_user') and user.has_perm('moderation.assign_roles')


def test_account_flags(people):
    clients, _ = people
    player = clients['Spieler'].client.get('/account').json()
    moderator = clients['Moderator'].client.get('/account').json()
    admin = clients['Chefin'].client.get('/account').json()
    assert (player['developer'], player['role'], player['staff']) == (False, 'user', False)
    assert (moderator['developer'], moderator['role'], moderator['staff']) == (True, 'moderator', True)
    assert (admin['developer'], admin['role'], admin['staff']) == (True, 'admin', True)


def test_staff_flag_alone_gives_no_rights(people, django_user_model):
    clients, users = people
    users['Spieler'].is_staff = True
    users['Spieler'].save()
    assert clients['Spieler'].client.get('/account').json()['developer'] is False
    assert clients['Spieler'].client.get('/developer').status_code == 403


def test_moderator_can_take_over_dispatch_player_cannot(people):
    clients, _ = people
    owner = clients['Spieler']
    owner.create()
    owner.api('take_ls')
    for name in ('Zweiter', 'Moderator'):
        clients[name].room = owner.room
        clients[name].join()
    dispatcher = owner.id
    refused = clients['Zweiter'].api('take_ls', replace_dispatcher=dispatcher)
    assert refused.status_code == 400 and refused.json()['error'] == 'Leitstelle ist bereits besetzt'
    taken = clients['Moderator'].api('take_ls', replace_dispatcher=dispatcher)
    assert taken.status_code == 200
    assert taken.json()['state']['dispatcher'] == clients['Moderator'].id


# ------------------------------------------------------------------ Rechte-Matrix im Admin

MATRIX = [
    # Pfad, Spieler, Moderator, Admin  (302 = zur Admin-Anmeldung umgeleitet)
    ('/admin/', 302, 200, 200),
    ('/admin/accounts/user/', 302, 200, 200),
    ('/admin/accounts/user/{target}/change/', 302, 200, 200),
    ('/admin/accounts/user/{target}/sperren/', 302, 200, 200),
    ('/admin/accounts/user/{target}/entsperren/', 302, 200, 200),
    ('/admin/accounts/user/{target}/rolle/', 302, 403, 200),
    ('/admin/moderation/room/', 302, 200, 200),
    ('/admin/moderation/ban/', 302, 200, 200),
    ('/admin/moderation/moderationevent/', 302, 200, 200),
    ('/admin/admin/logentry/', 302, 403, 200),
]


@pytest.mark.parametrize('path,as_player,as_moderator,as_admin', MATRIX)
def test_admin_permission_matrix(people, path, as_player, as_moderator, as_admin):
    _, users = people
    url = path.format(target=users['Zweiter'].pk)
    assert Client().get(url).status_code == 302  # nicht angemeldet
    for name, expected in (('Spieler', as_player), ('Moderator', as_moderator), ('Chefin', as_admin)):
        client = Client()
        client.force_login(users[name])
        assert client.get(url).status_code == expected, (name, url)


def test_moderator_cannot_edit_account(people):
    _, users = people
    client = admin_client(users['Moderator'])
    target = users['Zweiter']
    response = admin_post(client, f'/admin/accounts/user/{target.pk}/change/',
                          {'username': 'Umbenannt', 'email': 'x@example.com'})
    assert response.status_code == 403
    target.refresh_from_db()
    assert target.username == 'Zweiter'


def test_developer_stats_need_moderation(people):
    clients, _ = people
    assert clients['Spieler'].client.get('/developer').status_code == 403
    assert clients['Moderator'].client.get('/developer').status_code == 200


# ------------------------------------------------------------------ Sperren

def test_ban_ends_sessions_and_removes_from_rooms(people):
    clients, users = people
    owner, victim = clients['Zweiter'], clients['Spieler']
    owner.create()
    owner.api('take_ls')  # mit besetzter Leitstelle alarmiert die KI keine Fahrzeuge
    victim.room = owner.room
    victim.join()
    vehicle = next(v['id'] for v in rooms.rooms[owner.room]['vehicles'].values()
                   if v['phase'] == 'wache' and not v['incident'] and v['status'] != 6)
    claim = victim.api('claim', vehicle=vehicle)
    assert claim.status_code == 200, claim.json()

    client = admin_client(users['Moderator'])
    response = admin_post(client, f'/admin/accounts/user/{users["Spieler"].pk}/sperren/',
                          {'duration': '1d', 'reason': 'Beleidigungen im Funk'})
    assert response.status_code == 302

    r = rooms.rooms[owner.room]
    assert victim.id not in r['players']
    assert r['vehicles'][vehicle]['owner'] is None
    last = r['radio'][-1]['message']
    assert last.startswith('Spieler wurde aus dem Raum entfernt.')
    assert 'Beleidigung' not in last

    # Sitzung ist weg: /api und /account sehen keinen angemeldeten Spieler mehr.
    assert victim.api('state').status_code == 401
    assert victim.client.get('/account').json()['name'] is None

    ban = Ban.objects.get(user=users['Spieler'])
    assert ban.created_by == users['Moderator'] and ban.reason == 'Beleidigungen im Funk'
    assert timedelta(hours=23) < ban.ends_at - ban.starts_at <= timedelta(days=1)
    event = ModerationEvent.objects.get(action=ModerationEvent.BAN)
    assert (event.actor_name, event.target_name) == ('Moderator', 'Spieler')
    assert event.details['duration'] == '1 Tag' and event.details['rooms'] == [owner.room]


def test_ban_frees_dispatcher(people):
    clients, users = people
    owner, victim = clients['Zweiter'], clients['Spieler']
    owner.create()
    victim.room = owner.room
    victim.join()
    assert victim.api('take_ls').json()['state']['dispatcher'] == victim.id
    bans.ban_user(users['Moderator'], users['Spieler'], 'Trollen', '1h')
    r = rooms.rooms[owner.room]
    assert r['dispatcher'] is None
    assert r['radio'][-1]['message'] == 'Spieler wurde aus dem Raum entfernt. Die Leitstelle ist wieder frei.'


def test_banned_password_login_shows_end(people):
    clients, users = people
    ban = bans.ban_user(users['Moderator'], users['Spieler'], 'Spam', '7d')
    fresh = GameClient()
    response = fresh.account('login', name='Spieler', password=PASSWORD)
    assert response.status_code == 403
    expected = bans.local_time(ban.ends_at).strftime('%d.%m.%Y, %H:%M Uhr')
    assert response.json()['error'] == f'Dein Konto ist gesperrt bis {expected}.'
    # Falsches Passwort verrät die Sperre nicht.
    wrong = fresh.account('login', name='Spieler', password='falsch-falsch')
    assert wrong.json()['error'] == 'Benutzername oder Passwort stimmt nicht.'


def test_permanent_ban_message(people):
    _, users = people
    bans.ban_user(users['Chefin'], users['Spieler'], 'Betrug', 'perm')
    response = GameClient().account('login', name='Spieler', password=PASSWORD)
    assert response.json()['error'] == 'Dein Konto ist dauerhaft gesperrt.'


def test_banned_google_login(people, monkeypatch, django_user_model):
    _, users = people
    google_user = django_user_model.objects.create(username='Funk-abc', google_sub='g-1')
    bans.ban_user(users['Moderator'], google_user, 'Spam', '1h')
    monkeypatch.setattr(services, 'GOOGLE_CLIENT_ID', 'client-id')
    monkeypatch.setattr(services, 'verify_google', lambda credential: {'sub': 'g-1', 'nonce': 'n-1'})
    client = GameClient()
    client.client.cookies['wb_google_nonce'] = 'n-1'
    response = client.account('google', credential='token')
    assert response.status_code == 403
    assert response.json()['error'].startswith('Dein Konto ist gesperrt bis ')
    assert client.client.get('/account').json()['name'] is None


def test_banned_discord_login(people, monkeypatch, django_user_model):
    _, users = people
    discord_user = django_user_model.objects.create(username='Discordia', discord_sub='123456789')
    bans.ban_user(users['Moderator'], discord_user, 'Spam', 'perm')
    monkeypatch.setattr(discord, 'login_enabled', lambda: True)
    monkeypatch.setattr(discord, 'complete_login', lambda code, uri: {'id': '123456789', 'username': 'Discordia'})
    client = Client()
    client.cookies[discord.STATE_COOKIE] = 'state-1'
    response = client.get('/auth/discord/callback', {'code': 'c', 'state': 'state-1'})
    assert response['Location'] == '/?login_error=banned'
    account = client.get('/account').json()
    assert account['name'] is None
    assert account['loginNotice'] == 'Dein Konto ist dauerhaft gesperrt.'
    assert 'loginNotice' not in client.get('/account').json()  # nur einmal


def test_middleware_rejects_existing_session(people):
    """Sperre ohne Abmelden (z. B. direkt in der Datenbank angelegt): /api lehnt trotzdem ab."""
    clients, users = people
    player = clients['Spieler']
    player.create()
    Ban.objects.create(user=users['Spieler'], reason='direkt', ends_at=timezone.now() + timedelta(hours=1))
    response = player.api('state')
    assert response.status_code == 403
    assert response.json()['banned'] is True
    assert response.json()['error'].startswith('Dein Konto ist gesperrt bis ')
    assert player.client.get('/account').json()['name'] is None  # abgemeldet


def test_expired_ban_no_longer_applies(people):
    _, users = people
    ban = bans.ban_user(users['Moderator'], users['Spieler'], 'kurz', '1h')
    Ban.objects.filter(pk=ban.pk).update(starts_at=timezone.now() - timedelta(hours=2),
                                         ends_at=timezone.now() - timedelta(hours=1))
    bans.forget(users['Spieler'])
    assert bans.active_ban(users['Spieler']) is None
    response = GameClient().account('login', name='Spieler', password=PASSWORD)
    assert response.status_code == 200


def test_cached_ban_expires_without_cache_reset(people, monkeypatch):
    _, users = people
    bans.ban_user(users['Moderator'], users['Spieler'], 'kurz', '1h')
    with pytest.raises(bans.BannedError):
        bans.check_not_banned(users['Spieler'])
    later = bans.time.time() + 3601
    monkeypatch.setattr(bans.time, 'time', lambda: later)
    bans.check_not_banned(users['Spieler'])  # Cache-Eintrag ist abgelaufen, keine Sperre mehr


def test_nobody_bans_themselves(people):
    _, users = people
    for name in ('Moderator', 'Chefin'):
        with pytest.raises(ModerationError, match='nicht selbst'):
            bans.ban_user(users[name], users[name], 'Test', '1h')
    assert not Ban.objects.exists()


def test_moderator_cannot_ban_moderators_or_admins(people, django_user_model):
    _, users = people
    other_moderator = make_moderator(django_user_model.objects.create(username='Moderator2'))
    for target in (users['Chefin'], other_moderator):
        with pytest.raises(ModerationError, match='keine Moderatoren oder Admins'):
            bans.ban_user(users['Moderator'], target, 'Test', '1h')
    assert not Ban.objects.exists()


def test_admin_can_ban_moderator(people):
    _, users = people
    bans.ban_user(users['Chefin'], users['Moderator'], 'Missbrauch', '1d')
    assert bans.active_ban(users['Moderator'])


def test_player_cannot_ban(people):
    _, users = people
    with pytest.raises(ModerationError, match='Berechtigung'):
        bans.ban_user(users['Spieler'], users['Zweiter'], 'Test', '1h')


def test_ban_needs_reason_and_valid_duration(people):
    _, users = people
    with pytest.raises(ModerationError, match='Grund'):
        bans.ban_user(users['Moderator'], users['Spieler'], '  ', '1h')
    with pytest.raises(ModerationError, match='Dauer'):
        bans.ban_user(users['Moderator'], users['Spieler'], 'Test', '3y')


def test_new_ban_replaces_running_ban(people):
    _, users = people
    first = bans.ban_user(users['Moderator'], users['Spieler'], 'erst', '1h')
    second = bans.ban_user(users['Moderator'], users['Spieler'], 'dann länger', 'perm')
    first.refresh_from_db()
    assert first.lifted_at and first.lifted_by == users['Moderator']
    assert bans.active_ban(users['Spieler']) == second


def test_unban_via_admin(people):
    _, users = people
    bans.ban_user(users['Moderator'], users['Spieler'], 'Spam', 'perm')
    client = admin_client(users['Moderator'])
    response = admin_post(client, f'/admin/accounts/user/{users["Spieler"].pk}/entsperren/', {})
    assert response.status_code == 302
    assert bans.active_ban(users['Spieler']) is None
    assert GameClient().account('login', name='Spieler', password=PASSWORD).status_code == 200
    event = ModerationEvent.objects.get(action=ModerationEvent.UNBAN)
    assert (event.actor_name, event.target_name) == ('Moderator', 'Spieler')


def test_unban_without_active_ban(people):
    _, users = people
    with pytest.raises(ModerationError, match='keine aktive Sperre'):
        bans.lift_ban(users['Moderator'], users['Spieler'])


def test_bulk_ban_action_skips_protected_accounts(people):
    _, users = people
    client = admin_client(users['Moderator'])
    selected = [users['Spieler'].pk, users['Zweiter'].pk, users['Chefin'].pk]
    form = admin_post(client, '/admin/accounts/user/', {'action': 'ban_selected', '_selected_action': selected,
                                                       'index': 0})
    assert form.status_code == 200 and 'Konten sperren' in form.content.decode()
    done = admin_post(client, '/admin/accounts/user/', {
        'action': 'ban_selected', '_selected_action': selected, 'apply': '1',
        'duration': '1h', 'reason': 'Raid'})
    assert done.status_code == 302
    banned = set(Ban.objects.values_list('user__username', flat=True))
    assert banned == {'Spieler', 'Zweiter'}


def test_ban_filter_in_user_list(people):
    _, users = people
    bans.ban_user(users['Moderator'], users['Spieler'], 'Spam', '1h')
    client = admin_client(users['Chefin'])
    page = client.get('/admin/accounts/user/?sperre=aktiv').content.decode()
    assert 'Spieler' in page and 'Zweiter' not in page
    page = client.get('/admin/accounts/user/?rolle=moderator').content.decode()
    assert '>Moderator<' in page and 'Zweiter' not in page


# ------------------------------------------------------------------ Rollen vergeben

def test_admin_assigns_roles(people):
    _, users = people
    client = admin_client(users['Chefin'])
    response = admin_post(client, f'/admin/accounts/user/{users["Zweiter"].pk}/rolle/', {'role': 'moderator'})
    assert response.status_code == 302
    users['Zweiter'].refresh_from_db()
    assert roles.role_of(users['Zweiter']) == 'moderator' and users['Zweiter'].is_staff
    event = ModerationEvent.objects.get(action=ModerationEvent.ROLE)
    assert event.details == {'old': 'user', 'new': 'moderator'}

    admin_post(client, f'/admin/accounts/user/{users["Zweiter"].pk}/rolle/', {'role': 'user'})
    users['Zweiter'].refresh_from_db()
    assert roles.role_of(users['Zweiter']) == 'user' and not users['Zweiter'].is_staff


def test_moderator_cannot_assign_roles(people):
    _, users = people
    client = admin_client(users['Moderator'])
    response = admin_post(client, f'/admin/accounts/user/{users["Zweiter"].pk}/rolle/', {'role': 'admin'})
    assert response.status_code == 403
    assert roles.role_of(users['Zweiter']) == 'user'
    with pytest.raises(ModerationError, match='Nur Admins'):
        roles.set_role(users['Moderator'], users['Zweiter'], 'moderator')


def test_admin_cannot_change_own_role(people):
    _, users = people
    with pytest.raises(ModerationError, match='eigene Rolle'):
        roles.set_role(users['Chefin'], users['Chefin'], 'user')


def test_demoting_superuser_removes_superuser_flag(people, django_user_model):
    _, users = people
    superuser = django_user_model.objects.create(username='Super', is_superuser=True, is_staff=True)
    roles.set_role(users['Chefin'], superuser, 'moderator')
    superuser.refresh_from_db()
    assert not superuser.is_superuser and roles.role_of(superuser) == 'moderator'


# ------------------------------------------------------------------ Räume im Admin

def test_rooms_page_lists_players(people):
    clients, users = people
    clients['Spieler'].create()
    page = admin_client(users['Moderator']).get('/admin/moderation/room/').content.decode()
    assert f'Raum {clients["Spieler"].room}' in page
    assert 'Spieler' in page and 'Raumbesitzer' in page


def test_kick_from_admin(people):
    clients, users = people
    owner, victim = clients['Zweiter'], clients['Spieler']
    owner.create()
    victim.room = owner.room
    victim.join()
    client = admin_client(users['Moderator'])
    response = admin_post(client, '/admin/moderation/room/entfernen/', {'room': owner.room, 'player': victim.id})
    assert response.status_code == 302
    kicked = victim.api('state')
    assert kicked.status_code == 403
    assert kicked.json() == {'error': rooms.KICKED_MODERATION, 'kicked': True}
    assert rooms.rooms[owner.room]['radio'][-1]['message'] == 'Spieler wurde von der Moderation aus dem Raum entfernt.'
    assert victim.join()  # keine Raumsperre: wieder beitreten geht
    event = ModerationEvent.objects.get(action=ModerationEvent.KICK)
    assert (event.target_name, event.room_code) == ('Spieler', owner.room)


def test_moderator_cannot_kick_admin(people):
    clients, users = people
    admin_player = clients['Chefin']
    admin_player.create()
    client = admin_client(users['Moderator'])
    admin_post(client, '/admin/moderation/room/entfernen/', {'room': admin_player.room, 'player': admin_player.id})
    assert admin_player.id in rooms.rooms[admin_player.room]['players']
    assert not ModerationEvent.objects.exists()


def test_close_room(people):
    clients, users = people
    owner = clients['Spieler']
    owner.create()
    code = owner.room
    client = admin_client(users['Moderator'])
    response = admin_post(client, '/admin/moderation/room/schliessen/', {'room': code})
    assert response.status_code == 302
    assert code not in rooms.rooms
    closed = owner.api('state')
    assert closed.status_code == 403 and closed.json() == {'error': rooms.CLOSED, 'kicked': True}
    event = ModerationEvent.objects.get(action=ModerationEvent.CLOSE_ROOM)
    assert event.room_code == code and event.details['players'] == ['Spieler']


def test_player_cannot_use_room_moderation(people):
    clients, users = people
    clients['Zweiter'].create()
    client = Client()
    client.force_login(users['Spieler'])
    response = client.post('/admin/moderation/room/schliessen/', {'room': clients['Zweiter'].room})
    assert response.status_code in (302, 403)
    assert clients['Zweiter'].room in rooms.rooms


def test_banned_owner_hands_room_over(people):
    clients, users = people
    owner, guest = clients['Spieler'], clients['Zweiter']
    owner.create()
    guest.room = owner.room
    guest.join()
    bans.ban_user(users['Moderator'], users['Spieler'], 'Spam', '1h')
    r = rooms.rooms[owner.room]
    assert r['owner_account'] == users['Zweiter'].pk and r['admin'] == guest.id


# ------------------------------------------------------------------ Protokoll und Schutz

def test_audit_log_filter(people):
    _, users = people
    bans.ban_user(users['Moderator'], users['Spieler'], 'Spam', '1h')
    bans.lift_ban(users['Moderator'], users['Spieler'])
    client = admin_client(users['Moderator'])
    response = client.get('/admin/moderation/moderationevent/?action=ban')
    assert [event.action for event in response.context['cl'].result_list] == ['ban']
    assert 'Grund: Spam' in response.content.decode()
    response = client.get('/admin/moderation/moderationevent/?q=Spieler')
    assert {event.action for event in response.context['cl'].result_list} == {'ban', 'unban'}


def test_admin_post_from_foreign_origin_is_rejected(people):
    _, users = people
    client = admin_client(users['Moderator'])
    response = client.post(f'/admin/accounts/user/{users["Spieler"].pk}/sperren/',
                           {'duration': '1h', 'reason': 'x', 'csrfmiddlewaretoken': client.cookies['csrftoken'].value},
                           headers={'Origin': 'https://boese.example'})
    assert response.status_code == 403
    assert not Ban.objects.exists()


def test_admin_post_without_csrf_is_rejected(people):
    _, users = people
    client = admin_client(users['Moderator'])
    response = client.post(f'/admin/accounts/user/{users["Spieler"].pk}/sperren/', {'duration': '1h', 'reason': 'x'})
    assert response.status_code == 403
    assert not Ban.objects.exists()


def test_admin_posts_are_rate_limited(people, settings):
    _, users = people
    settings.RATE_LIMITS = {**settings.RATE_LIMITS, 'moderation': '2/m'}
    client = admin_client(users['Moderator'])
    statuses = [admin_post(client, '/admin/moderation/room/schliessen/', {'room': 'XXXXXX'}).status_code
                for _ in range(3)]
    assert statuses == [302, 302, 429]


def test_moderator_sees_no_password_reset_link(people):
    _, users = people
    url = f'/admin/accounts/user/{users["Zweiter"].pk}/change/'
    moderator_page = admin_client(users['Moderator']).get(url).content.decode()
    admin_page = admin_client(users['Chefin']).get(url).content.decode()
    assert '../password/' not in moderator_page and 'Sperrhistorie' in moderator_page
    assert '../password/' in admin_page
