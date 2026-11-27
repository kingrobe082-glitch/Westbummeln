"""gunicorn-Konfiguration für den Docker-Container (deploy/docker-compose.prod.yml).

Genau EIN Worker: Die Spielräume liegen im Arbeitsspeicher dieses einen Prozesses (game/rooms.py).
Ein zweiter Worker hätte eigene, leere Räume, Spieler sähen sich gegenseitig nicht mehr.
Parallelität kommt aus den Threads. Kein preload: wsgi.py startet die Discord-Threads im Worker.
"""
import os

from gunicorn.glogging import Logger

# Im Container auf allen Schnittstellen; nach außen ist Port 8000 nicht veröffentlicht,
# erreichbar ist er nur für Caddy über das Docker-Netz.
bind = '0.0.0.0:8000'
workers = 1  # FEST, siehe oben. Nicht über eine Variable änderbar.
worker_class = 'gthread'
threads = 8
timeout = 30
# Beim Beenden (Deploy) wartet der Worker so lange auf laufende Anfragen und sichert danach die Räume
# (worker_exit unten). stop_grace_period in docker-compose.prod.yml muss größer sein.
graceful_timeout = 30
keepalive = 5

# Grenzen für Anfragezeilen und Header (Standardwerte von gunicorn, hier ausdrücklich).
limit_request_line = 4094
limit_request_fields = 50
limit_request_field_size = 8190

# Zugriffs-Log nach stdout (docker compose logs web). %(U)s ist der Pfad OHNE Query-String:
# so landen keine OAuth-Codes (Discord-Callback ?code=…) oder andere Parameter im Log.
accesslog = '-'
access_log_format = '%(h)s %(t)s "%(m)s %(U)s %(H)s" %(s)s %(b)s %(L)s'
errorlog = '-'
loglevel = os.environ.get('GUNICORN_LOGLEVEL', 'info')


class QuietHealthcheckLogger(Logger):
    """Lässt erfolgreiche /healthz-Abfragen (Docker-Healthcheck) im Zugriffs-Log weg."""

    def access(self, resp, req, environ, request_time):
        if environ.get('PATH_INFO') == '/healthz' and resp.status_code == 200:
            return
        super().access(resp, req, environ, request_time)


logger_class = QuietHealthcheckLogger

# X-Forwarded-Proto/-For nur von Caddy glauben. Caddy hat im Compose-Netz "frontend" die feste
# Adresse CADDY_IP (docker-compose.prod.yml, setzt FORWARDED_ALLOW_IPS). Niemals "*".
# gunicorn 23 kennt hier keine Netze (CIDR), nur einzelne Adressen.
forwarded_allow_ips = os.environ.get('FORWARDED_ALLOW_IPS', '10.250.53.10')


def worker_exit(server, worker):
    """Läuft im Worker-Prozess, nachdem er die letzte Anfrage beantwortet hat (SIGTERM beim Deploy):
    alle Spielräume in ROOM_STATE_FILE sichern, damit der neue Container sie wieder lädt."""
    try:
        from game import persistence
    except Exception:  # Worker ist schon beim Laden der App gescheitert: nichts zu sichern
        return
    persistence.shutdown()
