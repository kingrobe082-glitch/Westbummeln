"""Fehlerbehandlung von /api und /account: Spieler sehen deutsche Meldungen, das Log bekommt die Details."""
import logging

import pytest

from accounts import services
from game import engine, rooms
from game.parsing import to_int


def records(caplog, logger, level):
    return [r for r in caplog.records if r.name == logger and r.levelno == level]


# ------------------------------------------------------------------ Serverfehler werden geloggt

def test_api_server_error_is_logged_with_context(player, monkeypatch, caplog):
    player.create()

    def broken(r, now):
        raise RuntimeError('kaputt')

    monkeypatch.setattr(engine, 'update', broken)
    response = player.api('state')
    assert response.status_code == 500
    assert response.json() == {'error': 'Serverfehler'}
    [record] = records(caplog, 'game.views', logging.ERROR)
    message = record.getMessage()
    assert "'state'" in message and repr(player.room) in message and 'Konto ' in message
    assert 'Konto None' not in message
    assert record.exc_info[0] is RuntimeError


def test_account_server_error_is_logged_without_personal_data(game_client, monkeypatch, caplog):
    def broken(data):
        raise RuntimeError('doppelter Name ' + data['email'])  # wie eine Datenbankmeldung

    monkeypatch.setattr(services, 'register', broken)
    response = game_client().account('register', name='Geheimname', email='geheim@example.com',
                                     password='Funkgeraet-42')
    assert response.status_code == 500
    assert response.json() == {'error': 'Serverfehler'}
    [record] = records(caplog, 'accounts.views', logging.ERROR)
    message = record.getMessage()
    assert "'register'" in message and 'RuntimeError' in message and 'broken' in message
    assert 'geheim' not in caplog.text.lower() and 'Funkgeraet' not in caplog.text


# ------------------------------------------------------------------ Keine Python-Fehlertexte an Spieler

def test_status_must_be_a_number(player):
    player.create()
    assert player.api('claim', vehicle='WB-3-HLF20').status_code == 200
    response = player.api('status', status='abc')
    assert response.status_code == 400
    assert response.json() == {'error': 'Status: bitte eine ganze Zahl angeben.'}


def test_seats_must_be_a_number(player):
    player.create()
    response = player.api('settings', kind='vehicle', vehicle='WB-3-HLF20', call='HLF', seats=None)
    assert response.json() == {'error': 'Sitzplätze: bitte eine ganze Zahl angeben.'}


@pytest.mark.parametrize('since', ['abc', float('inf'), float('nan'), [1]])
def test_voice_poll_since_must_be_a_number(player, since):
    player.create()
    response = player.api('voice_poll', since=since)
    assert response.status_code == 400
    assert response.json() == {'error': 'Nachrichtennummer: bitte eine ganze Zahl angeben.'}


def test_unexpected_key_error_is_hidden_and_logged(player, monkeypatch, caplog):
    player.create()

    def broken(*args):
        raise KeyError('geheimer-schluessel')

    monkeypatch.setattr(rooms, 'handle', broken)
    response = player.api('state')
    assert response.status_code == 400
    assert response.json() == {'error': 'Ungültige Anfrage.'}
    [record] = records(caplog, 'game.views', logging.WARNING)
    assert "'state'" in record.getMessage() and record.exc_info[0] is KeyError


def test_type_error_in_account_is_hidden_and_logged(game_client, monkeypatch, caplog):
    def broken(data):
        raise TypeError("unsupported operand type(s) for +: 'int' and 'str'")

    monkeypatch.setattr(services, 'register', broken)
    response = game_client().account('register', name='Neu', email='neu@example.com', password='Funkgeraet-42')
    assert response.status_code == 400
    assert response.json() == {'error': 'Ungültige Anfrage.'}
    [record] = records(caplog, 'accounts.views', logging.WARNING)
    assert 'TypeError' in record.getMessage()


@pytest.mark.parametrize('body', ['{kaputt', '[1, 2]', '"text"', b'\xff\xfe'])
@pytest.mark.parametrize('path', ['/api', '/account'])
def test_broken_json_is_ungueltige_anfrage(player, path, body):
    response = player.client.post(path, body, content_type='application/json',
                                  headers={'X-CSRFToken': player.token()})
    assert response.status_code == 400
    assert response.json() == {'error': 'Ungültige Anfrage.'}


def test_intentional_german_errors_stay(player):
    player.create()
    response = player.api('status', status=9)
    assert response.json() == {'error': 'Bitte Fahrzeug übernehmen'}


def test_to_int():
    assert to_int('7', 'Status') == 7
    assert to_int(3.0, 'Status') == 3
    with pytest.raises(ValueError, match='^Status: bitte eine ganze Zahl angeben.$'):
        to_int('abc', 'Status')
