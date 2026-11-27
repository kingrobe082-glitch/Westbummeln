# Überwachung: Wer merkt, wenn der Server nachts ausfällt?

Zwei kostenlose Dienste **außerhalb** von AWS schicken dir eine Mail (und auf Wunsch eine
Push-Nachricht), wenn etwas nicht stimmt:

| Was | Dienst | Wie |
|---|---|---|
| Spiel nicht erreichbar (Server, Caddy oder `web` aus) | **UptimeRobot** | ruft alle 5 min `https://planspiel.7z2.de/healthz` auf |
| tägliche Sicherung ausgeblieben oder fehlgeschlagen | **healthchecks.io** | der Container `backup` meldet sich nach jeder Sicherung; bleibt die Meldung aus, warnt der Dienst |

## Warum extern und nicht selbst gehostet?

Ein Monitor auf demselben Server (z. B. Uptime Kuma) fällt mit dem Server aus und kann dann
niemanden mehr warnen. Genau den wichtigsten Fall – Server nachts weg – sähe er nie. Außerdem
kostet er RAM, den die t3.micro nicht übrig hat. Die beiden Dienste oben sind für diesen Umfang
kostenlos (UptimeRobot: 50 Monitore, 5-min-Takt; healthchecks.io: 20 Checks) und brauchen auf dem
Server nichts außer einer URL in `.env`.

Warum zwei Dienste? UptimeRobot prüft von außen, ob etwas **da** ist. healthchecks.io merkt, wenn
etwas **ausbleibt** (die Sicherung um 03:00). Das kann der jeweils andere nicht gut.

## So funktioniert der Backup-Ping

- `backup-hooks/10-healthchecks` wird vom Backup-Image bei jeder Sicherung aufgerufen
  (auch bei `docker compose exec backup /backup.sh` von Hand).
- Es ruft `BACKUP_PING_URL/start` (Sicherung beginnt), dann `BACKUP_PING_URL` (fertig) oder
  `BACKUP_PING_URL/fail` (fehlgeschlagen, z. B. Datenbank nicht erreichbar).
- `BACKUP_PING_URL` leer oder nicht gesetzt = kein Ping, alles läuft wie vorher.
- Ist healthchecks.io nicht erreichbar, läuft die Sicherung trotzdem durch (Warnung im Log).
- Damit `backup` ins Internet kommt, hängt der Container zusätzlich im Netz `frontend`.

## Einrichten (einmalig, ca. 15 Minuten)

Voraussetzung: Der PR mit dieser Datei ist gemergt und deployt.

1. **UptimeRobot-Konto anlegen:** <https://uptimerobot.com> → **Register for FREE** → mit
   `verify@von-roda.de` registrieren und die Bestätigungsmail anklicken.
2. **HTTP-Monitor anlegen:** im Dashboard **+ New monitor** →
   Monitor type **HTTP / website monitoring** →
   URL `https://planspiel.7z2.de/healthz` →
   Monitor interval **5 minutes** →
   unter „How will we notify you?“ **E-mail** angehakt lassen →
   **Create monitor**. Nach ein paar Minuten steht dort grün **Up**.
   Push aufs Handy (optional): App „UptimeRobot“ installieren, mit demselben Konto anmelden,
   Benachrichtigungen erlauben.
3. **healthchecks.io-Konto anlegen:** <https://healthchecks.io> → **Sign Up** → `verify@von-roda.de`
   eintragen → Link aus der Mail anklicken. Du landest im Projekt „My Project“; dort gibt es schon
   einen Beispiel-Check, den kannst du löschen (Check anklicken → **Remove**).
4. **Check „Backup täglich“ anlegen:** **+ Add Check** →
   Name `Backup täglich` →
   Schedule: Reiter **Cron** →
   Cron Expression `0 3 * * *` →
   Server's Time Zone `Europe/Berlin` →
   Grace Time **1 hour** →
   **Save**. Danach den Check öffnen und unter „How To Ping“ die **Ping-URL** kopieren
   (sieht aus wie `https://hc-ping.com/1a2b3c4d-…`). Mail-Benachrichtigung ist unter
   **Integrations** schon eingeschaltet.
5. **Auf den Server:**

   ```bash
   ssh deploy@planspiel.7z2.de
   cd /opt/westbummeln
   ```

6. **Ping-URL in `.env` eintragen** – in der ersten Zeile `DEINE-PING-URL` durch die kopierte URL
   ersetzen, dann alle vier Zeilen einfügen:

   ```bash
   URL='DEINE-PING-URL'
   grep -q '^BACKUP_PING_URL=' .env || echo 'BACKUP_PING_URL=' >> .env
   sed -i "s|^BACKUP_PING_URL=.*|BACKUP_PING_URL=$URL|" .env
   docker compose up -d backup
   ```

   Prüfen: `grep BACKUP_PING_URL .env` zeigt deine URL.
7. **Test auslösen:**

   ```bash
   docker compose exec backup /backup.sh
   ```

   Am Ende stehen zwei Zeilen `Ping gesendet (…) an hc-ping.com`. In healthchecks.io wird der Check
   nach ein paar Sekunden grün (**up**), unter „Events“ siehst du „Started“ und „OK“.
   Steht dort `WARNUNG: Ping … fehlgeschlagen`: URL in `.env` prüfen (Schritt 6).
8. **Fertig.** Ab jetzt meldet sich healthchecks.io, wenn bis 04:00 keine erfolgreiche Sicherung
   kam, und UptimeRobot, wenn die Seite länger als ein paar Minuten nicht antwortet. Beide melden
   sich auch, wenn wieder alles läuft.

## Was passiert bei einer Warnung?

| Mail von | Bedeutet | Zuerst nachsehen |
|---|---|---|
| UptimeRobot „Monitor is DOWN“ | Seite nicht erreichbar | `RUNBOOK.md` → Abschnitt 7 „Fehlerbilder“; `docker compose ps` |
| healthchecks.io „Backup täglich is DOWN“ | keine Sicherung seit über 25 h | `docker compose logs --tail=50 backup`, `ls -l backups/last` |
| healthchecks.io, Event „Failure“ | Sicherung ist gescheitert | `docker compose logs --tail=50 backup` (meist Datenbank nicht erreichbar oder Platte voll) |

## Grenzen

- `/healthz` antwortet, sobald `web` läuft, prüft aber die Datenbank nicht. Ist nur `db` kaputt,
  bleibt UptimeRobot grün; das Spiel zeigt dann Fehler beim Anmelden.
- Volle Platte oder voller Speicher melden die Dienste erst, wenn dadurch die Seite oder die
  Sicherung ausfällt.
- Die Ping-URL ist das einzige Geheimnis des Checks (wer sie kennt, kann „OK“ melden). Sie steht nur
  in `.env`, das Skript schreibt nur `hc-ping.com` ins Log.

## Abschalten

`BACKUP_PING_URL=` (leer) in `.env`, dann `docker compose up -d backup`. Den Check in healthchecks.io
löschen oder pausieren (**Pause**), sonst meldet er „down“.
