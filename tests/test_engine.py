"""Spiellogik ohne Django: gleiche Abläufe und Meldungen wie im alten server.py."""
import pytest

from game import engine

NOW = 1_000_000.0


@pytest.fixture
def room():
    r = engine.new_room('WB')
    r['weather_mode'] = 'manual'  # kein Wetterwechsel, damit Fahrzeiten fest 12 s sind
    return r


def join(r, account, name, now=NOW):
    return engine.handle(r, {'action': 'join'}, account, name, False, now)['id']


def act(r, pid, account, action, now=NOW, developer=False, **data):
    return engine.handle(r, {'action': action, 'id': pid, **data}, account, 'x', developer, now)


def test_fleet_has_18_vehicles_on_station(room):
    assert len(room['vehicles']) == 18
    assert room['vehicles']['WB-1-HLF20']['call'] == 'Florian WB 1 HLF 20'
    assert all(v['phase'] == 'wache' and v['status'] == 2 for v in room['vehicles'].values())


def test_join_makes_first_player_admin(room):
    pid = join(room, 1, 'Anna')
    assert room['admin'] == pid
    assert room['radio'][-1]['message'] == 'Anna ist beigetreten.'
    assert room['rev'] == 1


def test_foreign_player_id_is_rejected(room):
    pid = join(room, 1, 'Anna')
    with pytest.raises(ValueError, match='Sitzung abgelaufen – bitte neu beitreten'):
        act(room, pid, 2, 'state')


def test_full_mission_flow(room):
    ls = join(room, 1, 'Anna')
    gf = join(room, 2, 'Ben')
    act(room, ls, 1, 'take_ls')
    assert room['dispatcher'] == ls
    with pytest.raises(ValueError, match='Leitstelle ist bereits besetzt'):
        act(room, gf, 2, 'take_ls')
    act(room, gf, 2, 'claim', vehicle='WB-2-LF20')
    act(room, ls, 1, 'incident', title='F2 · Wohnungsbrand', address='Hauptstraße 5')
    inc = room['incidents'][-1]
    assert inc['pos'] == [.39, .53]
    act(room, ls, 1, 'dispatch', incident=inc['id'], vehicle='WB-2-LF20')
    vehicle = room['vehicles']['WB-2-LF20']
    assert (vehicle['phase'], vehicle['status']) == ('anfahrt', 3)

    engine.update(room, NOW + 12)
    assert (vehicle['phase'], vehicle['status']) == ('vorort', 4)
    act(room, gf, 2, 'work', now=NOW + 12, incident=inc['id'])
    engine.update(room, NOW + 100)
    assert inc['closed'] and inc['progress'] == 100
    assert vehicle['phase'] == 'rueckfahrt'
    engine.update(room, NOW + 112)
    assert (vehicle['phase'], vehicle['status'], vehicle['incident']) == ('wache', 2, None)


def test_take_ls_twice_does_not_change_revision(room):
    ls = join(room, 1, 'Anna')
    act(room, ls, 1, 'take_ls')
    rev = room['rev']
    act(room, ls, 1, 'take_ls')
    assert room['rev'] == rev


def test_developer_can_replace_dispatcher(room):
    ls = join(room, 1, 'Anna')
    dev = join(room, 2, 'Dev')
    act(room, ls, 1, 'take_ls')
    act(room, dev, 2, 'take_ls', developer=True, replace_dispatcher=ls)
    assert room['dispatcher'] == dev
    assert room['players'][ls]['role'] == 'none'


def test_incident_at_station_is_refused(room):
    ls = join(room, 1, 'Anna')
    act(room, ls, 1, 'take_ls')
    with pytest.raises(ValueError, match='Straße nicht bekannt'):
        act(room, ls, 1, 'incident', title='F1', address='Mondweg')


def test_only_dispatcher_creates_incidents(room):
    pid = join(room, 1, 'Anna')
    with pytest.raises(ValueError, match='Nur die besetzte Leitstelle'):
        act(room, pid, 1, 'incident', title='F1', address='Marktplatz')


def test_radio_rate_limit(room):
    pid = join(room, 1, 'Anna')
    for _ in range(5):
        act(room, pid, 1, 'radio', message='Hallo')
    with pytest.raises(ValueError, match='Bitte warte kurz'):
        act(room, pid, 1, 'radio', message='Hallo')
    act(room, pid, 1, 'radio', now=NOW + 11, message='Wieder da')
    assert room['radio'][-1]['kind'] == 'funk'


def test_ai_creates_and_dispatches_incident_for_single_player(room, monkeypatch):
    monkeypatch.setattr(engine, 'AI_INCIDENT_TYPES', [('F1 · Kleinbrand', 1, 1)])
    join(room, 1, 'Anna')
    engine.update(room, NOW)
    assert len(room['incidents']) == 1
    inc = room['incidents'][0]
    assert inc['creator'] == 'KI-Leitstelle'
    assert len(inc['assigned']) == 1


def test_offline_players_are_removed(room):
    pid = join(room, 1, 'Anna')
    engine.clean_offline(room, NOW + 31)
    assert pid not in room['players']
    assert room['admin'] is None
    assert 'Verbindungsverlust' in room['radio'][-1]['message']


def test_voice_signal_roundtrip(room):
    a = join(room, 1, 'Anna')
    b = join(room, 2, 'Ben')
    assert act(room, a, 1, 'voice_signal', to=b, signal={'type': 'offer'}) == {'ok': True}
    polled = act(room, b, 2, 'voice_poll', since=0)
    assert polled['messages'][0]['from'] == a
    with pytest.raises(ValueError, match='Ungültiges Funksignal'):
        act(room, a, 1, 'voice_signal', to=b, signal={'type': 'hack'})


def test_settings_only_for_admin(room):
    admin = join(room, 1, 'Anna')
    other = join(room, 2, 'Ben')
    with pytest.raises(ValueError, match='Nur die Raumverwaltung'):
        act(room, other, 2, 'settings', kind='weather', mode='manual', weather='Regen')
    act(room, admin, 1, 'settings', kind='weather', mode='manual', weather='Nebel')
    assert engine.snapshot(room)['travel_time'] == 20


def test_unknown_action(room):
    pid = join(room, 1, 'Anna')
    with pytest.raises(ValueError, match='Unbekannte Aktion'):
        act(room, pid, 1, 'fly')


def test_radio_hook_receives_entries(room, monkeypatch):
    seen = []
    monkeypatch.setattr(engine, 'radio_hook', lambda code, entry: seen.append((code, entry['message'])))
    join(room, 1, 'Anna')
    assert seen == [('WB', 'Anna ist beigetreten.')]
