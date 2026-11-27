# Runbook Westbummeln-Server

Spiel: **https://planspiel.7z2.de**. Server: AWS eu-central-1, t3.micro (2 vCPU, ~900 MB RAM +
2 GB Swap), Ubuntu 26.04. Alles liegt in **`/opt/westbummeln`** und gehört dem Benutzer
**`deploy`**. Alle Befehle unten laufen als `deploy` in diesem Ordner:

```bash
ssh deploy@planspiel.7z2.de
cd /opt/westbummeln
```

Die öffentliche IP steht absichtlich nirgends fest im Repo: Ohne Elastic IP ändert sie sich bei
Stop/Start der Instanz. Aktuelle IP: AWS-Konsole (EC2 → Instanz → „Public IPv4 address“) oder
`nslookup planspiel.7z2.de 1.1.1.1`. Ändert sie sich, den A-Record von `planspiel.7z2.de` anpassen
(Abschnitt 5).

## Überblick

```
Internet ──80/443──▶ caddy ──web:8000──▶ web (gunicorn, 1 Worker, 8 Threads) ──▶ db (Postgres 17)
                     (HTTPS, Zertifikat)                                         ▲
                                                                     backup ─────┘ täglich 03:00
```

| Datei in `/opt/westbummeln` | Woher | Inhalt |
|---|---|---|
| `docker-compose.prod.yml`, `Caddyfile`, `*.sh`, `.env.example`, `RUNBOOK.md` | GitHub Action (aus `deploy/`) | werden bei jedem Deploy überschrieben, nie hier ändern |
| `.env` | einmalig `./env-init.sh`, danach von Hand | Domain und **alle Geheimnisse** (chmod 600) |
| `.deployed-tag`, `.deploy-history` | `remote-deploy.sh` | laufende Version, Liste aller Deploys |
| `backups/` | Container `backup`, `remote-deploy.sh` | Datenbank-Sicherungen |

- Nach außen offen sind nur 80 und 443 (TCP und UDP für HTTP/3) von Caddy. `web` und `db` haben
  keine veröffentlichten Ports. `db` hängt nur in einem internen Netz ohne Internet; `backup` zusätzlich im
  Netz `frontend`, damit es nach jeder Sicherung healthchecks.io anpingen kann (MONITORING.md).
- Die Daten liegen in Docker-Volumes: `westbummeln_db-data` (Datenbank) und
  `westbummeln_caddy-data` (Zertifikate). **Nie** `docker compose down -v` ausführen: `-v` löscht
  die Datenbank.
- Spielräume liegen im Arbeitsspeicher von `web`. Beim Herunterfahren und alle 30 s (bei Änderungen)
  sichert `web` sie nach `/app/state/rooms.json` im Volume `westbummeln_room-state` und lädt sie beim
  Start wieder (`game/persistence.py`). Ein Deploy oder Neustart unterbricht ein Spiel deshalb nur
  kurz („Server startet neu …“), Räume, Einsätze und Spieler bleiben. Nach einem Absturz fehlen
  höchstens die letzten 30 s. Ist die Datei unlesbar (z. B. Rollback auf eine ältere Version mit
  anderem Format), startet `web` mit leeren Räumen und legt sie als `rooms.json.broken` daneben.
  Alle laufenden Spiele bewusst beenden: `docker compose stop web`,
  `docker compose run --rm --no-deps --entrypoint rm web /app/state/rooms.json`, `docker compose up -d`.
- `.env` enthält `COMPOSE_FILE=docker-compose.prod.yml`, deshalb reicht überall `docker compose …`.

## 1. Erstinstallation

Voraussetzung (macht die Server-Einrichtung): Docker mit Compose-Plugin, Benutzer `deploy` in der
Gruppe `docker`, Ordner `/opt/westbummeln` mit `backups/` (Besitzer `deploy`), Firewall offen für
22, 80/tcp, 443/tcp und 443/udp, in der AWS-Security-Group ebenso.

1. **Dateien auf den Server.** Normalerweise kopiert die GitHub Action den Inhalt von `deploy/`
   beim ersten Lauf. Von Hand vom PC aus (PowerShell, im Repo-Ordner):

   ```powershell
   scp deploy/docker-compose.prod.yml deploy/Caddyfile deploy/remote-deploy.sh deploy/env-init.sh deploy/import-accounts.sh deploy/.env.example deploy/RUNBOOK.md deploy@planspiel.7z2.de:/opt/westbummeln/
   ```

   Auf dem Server danach `chmod +x *.sh`.

2. **`.env` anlegen** (einmalig, überschreibt nie eine vorhandene):

   ```bash
   ./env-init.sh planspiel.7z2.de deine-adresse@example.com
   nano .env
   ```

   Erzeugt zufällige Werte für `SECRET_KEY` und `POSTGRES_PASSWORD`. In `nano` noch
   `DEVELOPER_USERNAME` und `DEVELOPER_PASSWORD` (16–128 Zeichen) eintragen, optional Google und
   Discord. `ACME_EMAIL` bekommt Warnungen, falls ein Zertifikat nicht verlängert werden kann.
   Die Werte zusätzlich im Passwort-Manager ablegen: ohne `POSTGRES_PASSWORD` kommt man nicht
   mehr an die Datenbank.

3. **Erster Deploy.** Normalerweise per GitHub Action (Merge nach `main` oder „Run workflow“).
   Von Hand, falls nötig (`<sha>` ist ein Tag aus GHCR, Token mit `read:packages`):

   ```bash
   echo "<github-token>" | docker login ghcr.io -u <github-name> --password-stdin
   IMAGE_TAG=<sha> ./remote-deploy.sh
   docker logout ghcr.io
   ```

4. **Prüfen:**

   ```bash
   docker compose ps                       # alle "Up", web und db "(healthy)"
   curl -s https://planspiel.7z2.de/healthz      # -> ok
   docker compose logs caddy | grep -i certificate   # "certificate obtained successfully"
   ```

   Danach im Browser die Startseite öffnen, registrieren, anmelden, Raum betreten.

Alte Konten gibt es nicht zu übernehmen: Der Server startet leer, Spieler registrieren sich neu.
(`./import-accounts.sh <datei>` liest bei Bedarf eine Kontodatei im alten Format ein, mit
Probelauf und Rückfrage. Für die Neuinstallation wird es nicht gebraucht.)

## 2. Alltag

```bash
docker compose ps                             # Zustand
docker compose logs -f --tail=100 web         # Spiel-Log (Strg+C beendet nur die Anzeige)
docker compose logs --tail=100 caddy          # HTTPS/Zertifikate
docker compose logs --tail=50 backup          # letzte Sicherungen
docker stats --no-stream                      # Speicher je Container
cat .deployed-tag; tail -5 .deploy-history    # laufende Version, letzte Deploys
df -h /; docker system df                     # Plattenplatz
```

- **Neustart des Spiels:** `docker compose restart web` (laufende Spielräume gehen verloren).
- **`.env` geändert:** `docker compose up -d`. Compose erstellt die betroffenen Container neu und
  nimmt dabei die Version aus `IMAGE_TAG` in `.env` (setzt `remote-deploy.sh`).
- **Django-Befehle:** `docker compose exec web python manage.py <befehl>`, z. B. `createsuperuser`
  oder `shell`.
- **Datenbank direkt:** `docker compose exec db psql -U westbummeln westbummeln`.

## 3. Deploy und Rollback

Jeder Deploy läuft über `IMAGE_TAG=<sha> ./remote-deploy.sh`:

1. Image `ghcr.io/kingrobe082-glitch/westbummeln:<sha>` holen (scheitert das, bleibt alles wie es ist).
2. Datenbank nach `backups/pre-deploy/<zeit>_vor_<sha>.dump` sichern (die letzten 5 bleiben).
3. Stack starten. Beim Start führt `web` `migrate` und `bootstrap_accounts` aus.
4. Bis zu 90 s auf den Healthcheck von `web` warten. Ist `web` nicht gesund, startet automatisch
   wieder die vorherige Version und das Skript endet mit Exit-Code 1 (die Action wird rot).
5. Bei Erfolg: Tag nach `.deployed-tag`, `.deploy-history` und als `IMAGE_TAG` in `.env`; Caddy
   neu starten, falls sich das `Caddyfile` geändert hat; alte Images aufräumen (die 3 neuesten
   bleiben, dazu laufende und vorherige Version).

**Rollback von Hand** (z. B. Fehler, der erst im Spiel auffällt):

```bash
tail -5 .deploy-history                 # gewünschte ältere Version aussuchen
IMAGE_TAG=<älterer-sha> ./remote-deploy.sh
```

Ist das Image nicht mehr auf dem Server, holt das Skript es aus GHCR (vorher `docker login ghcr.io`,
siehe 1.3).

**Achtung Migrationen:** Hat die neuere Version das Datenbankschema geändert, läuft die ältere
Version auf dem neueren Schema. Neue Felder/Tabellen stören meist nicht. Startet die alte Version
trotzdem nicht oder verhält sie sich falsch: nach dem Rollback die Sicherung von **vor** dem
fehlerhaften Deploy einspielen (Abschnitt 4, „Sicherung vor einem Deploy“). Alles, was seitdem
passiert ist (neue Konten), geht dabei verloren.

## 4. Backups

| Ordner | Was | Aufbewahrung |
|---|---|---|
| `backups/daily/` | tägliche Sicherung 03:00 (`westbummeln-JJJJMMTT.sql.gz`) | 7 Tage |
| `backups/weekly/` | wöchentlich | 4 Wochen |
| `backups/monthly/` | monatlich | 3 Monate |
| `backups/last/` | letzte Sicherung mit Uhrzeit | wie daily |
| `backups/pre-deploy/` | vor jedem Deploy (`*.dump`, pg_dump-Custom-Format) | letzte 5 |

`*-latest.sql.gz` ist jeweils ein Verweis auf die neueste Datei.

**Sofort sichern:** `docker compose exec backup /backup.sh`

**Überwachung:** Ist `BACKUP_PING_URL` in `.env` gesetzt, meldet jede Sicherung sich bei
healthchecks.io; bleibt sie aus oder scheitert, kommt eine Mail. Einrichten: `MONITORING.md`.

**Auf den PC holen** (die Sicherungen liegen auf derselben Platte wie die Datenbank, ab und zu
eine Kopie ziehen), PowerShell:

```powershell
scp deploy@planspiel.7z2.de:/opt/westbummeln/backups/last/westbummeln-latest.sql.gz .
```

Die Dateien enthalten E-Mails und Passwort-Hashes: nie ins Repo, nicht weitergeben.

### Backup einspielen (Restore)

Lokal getestet: Konto nach der Sicherung angelegt, eingespielt, Konto war wieder weg, alle älteren
Konten und Anmeldungen funktionierten.

**Tägliche Sicherung (`.sql.gz`):**

1. Spiel und Sicherung anhalten, damit niemand schreibt:

   ```bash
   docker compose stop web backup
   ```

2. Vorsichtshalber den jetzigen Stand sichern:

   ```bash
   docker compose exec -T db pg_dump -U westbummeln -d westbummeln -Fc > backups/vor-restore-$(date +%Y%m%d-%H%M).dump
   ```

3. Sicherung einspielen (Datei anpassen). Die Sicherung löscht die vorhandenen Tabellen selbst
   (`--clean`), die Datenbank muss nicht neu angelegt werden:

   ```bash
   gunzip -c backups/daily/westbummeln-20261126.sql.gz \
     | docker compose exec -T db psql -U westbummeln -d westbummeln -v ON_ERROR_STOP=1 -q
   ```

   Am Ende erscheinen ein paar `setval`-Zeilen, keine `ERROR`-Zeile.

4. Wieder starten und prüfen:

   ```bash
   docker compose up -d
   docker compose ps
   docker compose exec web python manage.py shell -c "from accounts.models import User; print(User.objects.count())"
   ```

**Sicherung vor einem Deploy (`.dump`):** Schritte 1, 2 und 4 wie oben, Schritt 3 stattdessen:

```bash
docker compose exec -T db pg_restore -U westbummeln -d westbummeln --clean --if-exists --no-owner --exit-on-error \
  < backups/pre-deploy/<datei>.dump
```

`…_vor_<sha>.dump` ist der Stand, bevor `<sha>` ausgerollt wurde. Dazu passt die Version, die
davor lief (Zeile darüber in `.deploy-history`). Läuft gerade eine neuere Version, erst mit
`IMAGE_TAG=<passender-sha> ./remote-deploy.sh` zurückrollen, dann einspielen.

**Server komplett weg:** neuen Server einrichten, Erstinstallation (Abschnitt 1) mit der alten
`.env` aus dem Passwort-Manager, dann die vom PC kopierte Sicherung wie oben einspielen.

## 5. Domain, IP-Wechsel und Notlösung sslip.io

Die Domain ist `planspiel.7z2.de` (A-Record auf die öffentliche IP des Servers, kein AAAA-Record).
In `.env` steht `DOMAIN=planspiel.7z2.de`; `ALLOWED_HOSTS` und `CSRF_TRUSTED_ORIGINS` folgen über
`${DOMAIN}` automatisch.

**Öffentliche IP hat sich geändert** (Instanz gestoppt/gestartet, keine Elastic IP):

1. Neue IP in der AWS-Konsole ablesen.
2. Beim Domain-Anbieter den A-Record von `planspiel.7z2.de` auf die neue IP setzen.
3. Warten, bis `nslookup planspiel.7z2.de 1.1.1.1` die neue IP liefert. Am Server ist nichts zu
   ändern; Caddy behält sein Zertifikat.
4. Dauerhaft: der Instanz eine Elastic IP zuweisen, dann passiert das nicht mehr.

**Andere Domain:**

1. A-Record der neuen Domain auf die Server-IP setzen, mit `nslookup` prüfen.
2. In `.env` `DOMAIN=neue-domain.de` setzen. Sollen alte und neue Adresse eine Zeit lang beide gehen:
   `ALLOWED_HOSTS=${DOMAIN},planspiel.7z2.de` und
   `CSRF_TRUSTED_ORIGINS=https://${DOMAIN},https://planspiel.7z2.de`.
3. `docker compose up -d` – Caddy startet neu und holt das Zertifikat (`docker compose logs caddy`).
4. Google: in der Cloud Console den JavaScript-Ursprung `https://neue-domain.de` ergänzen.
   Discord: Redirect `https://neue-domain.de/auth/discord/callback` ergänzen (`DISCORD.md`).
5. Die alte Adresse auf die neue umleiten: im `Caddyfile` im Repo einen Block
   `planspiel.7z2.de { redir https://neue-domain.de{uri} permanent }` ergänzen und deployen.

**Notlösung ohne funktionierende Domain** (DNS kaputt, Domain abgelaufen): sslip.io löst
`<IP-mit-Bindestrichen>.sslip.io` auf diese IP auf, z. B. `1-2-3-4.sslip.io` → `1.2.3.4`.
In `.env` `DOMAIN=<IP-mit-Bindestrichen>.sslip.io` setzen und `docker compose up -d`; Caddy holt
dafür ein echtes Zertifikat. Google- und Discord-Anmeldung funktionieren unter dieser Adresse erst,
wenn sie dort ebenfalls eingetragen ist. Danach wieder auf `planspiel.7z2.de` zurückstellen.

## 6. Speicher

| Container | Grenze (`mem_limit`) | gemessen (lokal, nach Last) |
|---|---|---|
| web | 350 MB | ~90 MB |
| db | 256 MB (`shared_buffers=64MB`, `max_connections=30`, `work_mem=2MB`) | ~75 MB |
| caddy | 64 MB | ~20 MB |
| backup | 64 MB | ~2 MB (beim Sichern kurz mehr) |
| **Summe** | **734 MB** | **~190 MB** |

Wird ein Container wegen seiner Grenze beendet, steht in `docker inspect <container>` bei
`State.OOMKilled` `true`, und Docker startet ihn neu.

## 7. Fehlerbilder

| Symptom | Ursache / Abhilfe |
|---|---|
| Action rot, „ROLLBACK auf …“ | Neue Version startet nicht. `docker compose logs --tail=200 web` zeigt den Grund. Die alte Version läuft weiter. |
| `web` startet nicht, Log: „… fehlt“ | Pflichtwert in `.env` fehlt (`SECRET_KEY`, `DATABASE_URL`, `ALLOWED_HOSTS`). |
| Browser: 400 Bad Request | Aufgerufener Name steht nicht in `ALLOWED_HOSTS`. |
| Kein Zertifikat | Port 80 und 443 müssen aus dem Internet erreichbar sein (ufw **und** AWS-Security-Group), der A-Record von `DOMAIN` muss auf die aktuelle öffentliche IP zeigen (Abschnitt 5). Log: `docker compose logs caddy`. Bei Let's-Encrypt-Limits weicht Caddy auf ZeroSSL aus. |
| „docker compose config schlägt fehl“ | `.env` nicht lesbar (`ls -l .env`, Besitzer muss `deploy` sein) oder Pflichtwert fehlt. |
| Platte voll | `docker system df`, `docker image prune -a` (löscht alle nicht laufenden Images), alte Sicherungen in `backups/pre-deploy` löschen. |
