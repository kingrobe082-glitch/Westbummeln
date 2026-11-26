# Westbummeln – Multiplayer-Leitstelle

Browserspiel „Feuerwehr-Leitstelle“ für mehrere Spieler. Server: Django 5.2 mit Postgres
(lokal SQLite), ausgeliefert mit gunicorn und WhiteNoise in Docker hinter Caddy auf einem eigenen
Server.

## Aufbau

| Ordner | Inhalt |
|---|---|
| `westbummeln/` | Einstellungen (aus Umgebungsvariablen), URLs, WSGI |
| `accounts/` | Konten (eigenes User-Modell), Anmeldung mit Name/E-Mail, Google, Discord, Import alter Konten |
| `game/` | `engine.py` reine Spiellogik, `rooms.py` Spielräume im Speicher, `views.py` `POST /api` |
| `moderation/` | Rollen (Moderator, Admin), Sperren, Moderationsprotokoll, Admin-Seite „Aktive Räume“ (siehe `KONTEN.md`) |
| `integrations/` | Discord-Anbindung (siehe `DISCORD.md`) |
| `templates/`, `static/` | Spielseite, CSS, JavaScript, Karte |
| `tests/` | pytest-Tests |
| `deploy/` | Server-Betrieb: Docker Compose, Caddyfile, Deploy-, Backup- und Import-Skripte, `RUNBOOK.md` |
| `Dockerfile`, `entrypoint.sh`, `gunicorn.conf.py` | Produktions-Image |

Die Spielräume liegen im Arbeitsspeicher. Deshalb läuft der Server mit **genau einem**
gunicorn-Worker (mit 8 Threads).

## Lokal starten

Python 3.12 oder neuer installieren, dann im Ordner in PowerShell:

```powershell
python -m venv .venv
```

```powershell
.venv\Scripts\python -m pip install -r requirements-dev.txt
```

```powershell
.venv\Scripts\python manage.py migrate
```

```powershell
.venv\Scripts\python manage.py bootstrap_accounts
```

```powershell
.venv\Scripts\python manage.py runserver 8765
```

Danach `http://localhost:8765` öffnen. Lokal gibt es das Testkonto `test` / `test`.

## Tests

```powershell
.venv\Scripts\python -m pytest
```

```powershell
.venv\Scripts\ruff check .
```

GitHub Actions führt beides bei jedem Pull Request aus, einmal gegen Postgres und einmal gegen SQLite.

## Online (eigener Server mit Docker)

Das Spiel läuft unter **https://planspiel.7z2.de** auf einem eigenen Server (AWS) in Docker Compose:
**Caddy** (HTTPS, Zertifikat automatisch) → **web** (dieses Image, gunicorn) → **db** (Postgres 17),
dazu ein **backup**-Container mit täglicher Sicherung.

- Bei jedem Merge nach `main` baut eine GitHub Action das Image
  `ghcr.io/kingrobe082-glitch/westbummeln:<git-sha>` und ruft auf dem Server
  `deploy/remote-deploy.sh` auf. Startet die neue Version nicht, läuft automatisch wieder die alte.
- Beim Start laufen im Container automatisch `migrate` und `bootstrap_accounts`.
- Alle Geheimnisse stehen nur auf dem Server in `/opt/westbummeln/.env`
  (Vorlage: `deploy/.env.example`).

Wichtige Umgebungsvariablen:

| Variable | Wofür |
|---|---|
| `DJANGO_ENV` | `prod` auf dem Server (setzt Compose); dann sind die drei folgenden Pflicht |
| `DATABASE_URL` | Postgres-Verbindung |
| `SECRET_KEY` | Geheimer Django-Schlüssel |
| `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS` | Domain des Spiels |
| `DEVELOPER_USERNAME`, `DEVELOPER_PASSWORD` | erster Admin (siehe `KONTEN.md`) |
| `GOOGLE_CLIENT_ID` | Google-Anmeldung (siehe `KONTEN.md`) |
| `DISCORD_*` | Discord-Anbindung (siehe `DISCORD.md`) |

Betrieb (Erstinstallation, Logs, Rollback, Backup einspielen, Domain wechseln):
**`deploy/RUNBOOK.md`**. Umzug der alten Konten: `KONTEN.md`.

### Image lokal testen

```powershell
docker build -t ghcr.io/kingrobe082-glitch/westbummeln:local .
```

Danach wie in `deploy/docker-compose.local.yml` beschrieben den Stack mit `DOMAIN=localhost`
starten und `https://localhost` öffnen.
