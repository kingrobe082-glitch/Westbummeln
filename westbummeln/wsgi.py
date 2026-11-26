"""WSGI-Einstiegspunkt für gunicorn (und runserver).

Diese Datei wird nur von einem Prozess geladen, der wirklich Anfragen beantwortet. Deshalb starten
hier die Discord-Hintergrund-Threads: genau einmal pro Prozess, nie in Tests oder bei
manage.py-Befehlen wie migrate. gunicorn deshalb ohne --preload und mit genau 1 Worker starten,
denn der Spielzustand liegt im Speicher dieses einen Prozesses.
"""
import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'westbummeln.settings')

application = get_wsgi_application()

from game.rooms import start_background  # noqa: E402  (braucht geladene Django-Einstellungen)

start_background()
