"""Passwort-Hasher für die Konten aus dem alten Server (accounts.py).

Der alte Server speicherte scrypt(passwort, salt, n=2**15, r=8, p=1, dklen=64) und den 16-Byte-Salt
getrennt als Binärdaten. Beim Import werden beide zu wb_scrypt$<salt b64>$<hash b64> zusammengesetzt.
Weil dieser Hasher in PASSWORD_HASHERS nicht an erster Stelle steht, rechnet Django das Passwort beim
nächsten erfolgreichen Login automatisch mit dem Standard-Hasher neu.
"""
import base64
import hashlib
import secrets

from django.contrib.auth.hashers import BasePasswordHasher, mask_hash
from django.utils.crypto import constant_time_compare

N, R, P = 2**15, 8, 1
MAXMEM = 64 * 1024**2


def legacy_hash(password, salt):
    return hashlib.scrypt(password.encode(), salt=salt, n=N, r=R, p=P, maxmem=MAXMEM)


def encode_legacy(salt, hashed):
    """Baut aus den alten Binärspalten salt und password einen Django-Passwortwert."""
    return f'wb_scrypt${base64.b64encode(salt).decode()}${base64.b64encode(hashed).decode()}'


class LegacyScryptHasher(BasePasswordHasher):
    algorithm = 'wb_scrypt'

    def salt(self):
        return base64.b64encode(secrets.token_bytes(16)).decode()

    def encode(self, password, salt):
        return encode_legacy(base64.b64decode(salt), legacy_hash(password, base64.b64decode(salt)))

    def decode(self, encoded):
        algorithm, salt, hashed = encoded.split('$', 2)
        assert algorithm == self.algorithm
        return {'algorithm': algorithm, 'salt': salt, 'hash': hashed}

    def verify(self, password, encoded):
        decoded = self.decode(encoded)
        expected = legacy_hash(password, base64.b64decode(decoded['salt']))
        return constant_time_compare(base64.b64encode(expected).decode(), decoded['hash'])

    def safe_summary(self, encoded):
        decoded = self.decode(encoded)
        return {'Algorithmus': decoded['algorithm'], 'Salt': mask_hash(decoded['salt']),
                'Hash': mask_hash(decoded['hash'])}

    def must_update(self, encoded):
        return True

    def harden_runtime(self, password, encoded):
        pass
