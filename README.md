# Westbummeln – Multiplayer-Leitstelle

Browserspiel „Feuerwehr-Leitstelle“ für mehrere Spieler. Server: Django 5.2 mit Postgres
(lokal SQLite), ausgeliefert mit gunicorn und WhiteNoise auf Render.

## Aufbau

| Ordner | Inhalt |
|---|---|
| `westbummeln/` | Einstellungen (aus Umgebungsvariablen), URLs, WSGI |
| `accounts/` | Konten (eigenes User-Modell), Anmeldung mit Name/E-Mail, Google, Discord, Import alter Konten |
| `game/` | `engine.py` reine Spiellogik, `rooms.py` Spielräume im Speicher, `views.py` `POST /api` |
| `integrations/` | Discord-Anbindung (siehe `DISCORD.md`) |
| `templates/`, `static/` | Spielseite, CSS, JavaScript, Karte |
| `tests/` | pytest-Tests |

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

## Online bei Render

Die Datei `render.yaml` beschreibt Webdienst und Datenbank. Beim Start laufen automatisch
`migrate` und `bootstrap_accounts`, danach gunicorn. Wichtige Umgebungsvariablen:

| Variable | Wofür |
|---|---|
| `DATABASE_URL` | Postgres-Verbindung (von Render, Pflicht) |
| `SECRET_KEY` | Geheimer Django-Schlüssel (Pflicht, von Render erzeugt) |
| `DEVELOPER_USERNAME`, `DEVELOPER_PASSWORD` | Entwicklerkonto (siehe `KONTEN.md`) |
| `GOOGLE_CLIENT_ID` | Google-Anmeldung (siehe `KONTEN.md`) |
| `DISCORD_*` | Discord-Anbindung (siehe `DISCORD.md`) |

Den Umzug der alten Konten beschreibt `KONTEN.md`.
