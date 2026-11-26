"""gunicorn-Einstellungen. gunicorn liest diese Datei automatisch, wenn es im Projektordner startet.

Genau 1 Worker: Spielräume, IP-Limits und Login-Sperren liegen im Arbeitsspeicher dieses Prozesses.
Parallelität kommt über Threads (Frontend pollt alle 1,5 s).
"""
import os

bind = f"0.0.0.0:{os.environ.get('PORT', '8000')}"
workers = 1
worker_class = 'gthread'
threads = 8

# Hängende Anfragen beenden, beim Neustart laufenden Anfragen kurz Zeit geben.
timeout = 30
graceful_timeout = 20
# Verbindungen vom Render-Proxy offen halten. Schließt gunicorn früher als der Proxy, kann es
# vereinzelt 502-Fehler geben; deshalb länger als die üblichen 60 s Leerlauf eines Proxys.
keepalive = 65

# Grenzen für Anfragezeile und Header (gunicorn-Standards, hier ausdrücklich festgehalten),
# weniger Header als der Standard (100): Browser schicken etwa 20.
limit_request_line = 4094
limit_request_fields = 50
limit_request_field_size = 8190
