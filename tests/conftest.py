import json

import pytest
from django.core.cache import cache
from django.test import Client

from game import rooms


@pytest.fixture(autouse=True)
def fresh_server_state():
    """Spielräume, IP-Limits und Login-Sperren liegen im Prozessspeicher: vor jedem Test leeren."""
    rooms.rooms.clear()
    cache.clear()
    yield
    rooms.rooms.clear()


class GameClient:
    """Browser-Ersatz: hält Sitzung und CSRF-Cookie und schickt X-CSRFToken wie das Frontend."""

    def __init__(self):
        self.client = Client(enforce_csrf_checks=True)
        self.client.get('/')
        self.room = 'WESTBUMMELN'
        self.id = None

    def token(self):
        return self.client.cookies['csrftoken'].value

    def post(self, path, data, csrf=True):
        headers = {'X-CSRFToken': self.token()} if csrf else {}
        return self.client.post(path, json.dumps(data), content_type='application/json', headers=headers)

    def account(self, action, **fields):
        return self.post('/account', {'action': action, **fields})

    def api(self, action, **data):
        payload = {'action': action, 'room': self.room, 'id': self.id, **data}
        return self.post('/api', payload)

    def join(self):
        response = self.api('join')
        assert response.status_code == 200, response.json()
        self.id = response.json()['id']
        return response.json()['state']

    def create(self):
        """Neuen Raum erstellen; der Client ist danach Besitzer und schon beigetreten."""
        response = self.api('create_room')
        assert response.status_code == 200, response.json()
        self.room = response.json()['room']
        self.id = response.json()['id']
        return response.json()['state']


@pytest.fixture
def game_client(db):
    return GameClient


@pytest.fixture
def player(db):
    client = GameClient()
    response = client.account('register', name='Florian1', email='florian@example.com', password='Funkgeraet-42')
    assert response.status_code == 200, response.json()
    return client
