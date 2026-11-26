#!/bin/sh
# Startet den Webdienst: erst Datenbank-Migrationen und Konten-Einrichtung, dann gunicorn.
# Nur beim Start von gunicorn, damit z. B. `docker compose run --rm web python manage.py shell`
# nicht nebenbei migriert. Schlägt migrate fehl, startet gunicorn nicht, der Healthcheck bleibt
# rot und remote-deploy.sh rollt auf die vorherige Version zurück.
set -eu

if [ "${1:-}" = "gunicorn" ]; then
  python manage.py migrate --noinput
  python manage.py bootstrap_accounts
  # Abgelaufene Sitzungen löschen; im laufenden Betrieb erledigt das datenschutz.middleware stündlich.
  python manage.py clearsessions
fi

exec "$@"
