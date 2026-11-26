# Westbummeln-Konten

Die Konten liegen in einer **Postgres-Datenbank** auf dem eigenen Server (Container `db` in
`/opt/westbummeln`, Daten im Docker-Volume `westbummeln_db-data`). Lokal und in den Tests nimmt das
Spiel automatisch eine SQLite-Datei (`db.sqlite3`), wenn keine `DATABASE_URL` gesetzt ist.

In Produktion (`DJANGO_ENV=prod`) startet der Dienst absichtlich **nicht**, wenn `DATABASE_URL`,
`SECRET_KEY` oder `ALLOWED_HOSTS` fehlen. So kann er nie unbemerkt mit einer leeren
Wegwerf-Datenbank laufen und Konten verlieren. Schlägt ein Deploy deshalb fehl, rollt
`remote-deploy.sh` auf die vorherige Version zurück.

Gesichert wird täglich um 03:00 nach `/opt/westbummeln/backups` (7 Tage, 4 Wochen, 3 Monate),
zusätzlich vor jedem Deploy nach `backups/pre-deploy`. Einspielen: `deploy/RUNBOOK.md`.

---

## Umzug der alten Konten vom Render-Server (einmalig)

> Alle Spieler werden nach dem Umzug einmal abgemeldet und müssen sich neu anmelden.
> Passwörter bleiben gültig.

Voraussetzung: Der neue Server läuft (Erstinstallation in `deploy/RUNBOOK.md`) und die Startseite
lädt unter der neuen Adresse.

### 1. Alte Konten herunterladen

1. Auf GitHub dein **privates** Backup-Repo des alten Servers öffnen (z. B. `westbummeln-backup`).
2. Die Datei `accounts-backup.json` öffnen und rechts oben auf **Download raw file** klicken.
3. Möglichst spät herunterladen: Der alte Server sichert bei jeder Registrierung und beim
   Herunterfahren. Am besten erst den alten Dienst bei Render anhalten (**Suspend Service**), dann
   herunterladen. Dann ist auch das letzte neue Konto dabei.
4. Die Datei **niemals** ins öffentliche Spiel-Repo legen. Sie enthält E-Mails und Passwort-Hashes.

Statt der JSON-Datei geht auch eine alte `accounts.sqlite3`.

### 2. Datei auf den Server kopieren

Vom PC aus in PowerShell (Pfad anpassen):

```powershell
scp "C:\Pfad\zu\accounts-backup.json" deploy@63.183.198.23:/opt/westbummeln/
```

### 3. Importieren

Auf dem Server:

```bash
cd /opt/westbummeln
./import-accounts.sh accounts-backup.json
```

Das Skript kopiert die Datei in den laufenden Webdienst, macht zuerst einen **Probelauf**, der
nichts speichert, und fragt dann „Jetzt wirklich importieren? [j/N]“. Mit `j` wird importiert,
danach wird die Kopie im Container gelöscht. Die Datei auf dem Server danach selbst löschen:

```bash
rm accounts-backup.json
```

Der Import kann gefahrlos mehrmals laufen. Ein zweiter Lauf meldet „Neu übernommen: 0“ und ändert
nichts.

**Was der Import macht:**
- Konten behalten ihre alte ID, Name, E-Mail, Google- und Discord-Verknüpfung. Ist die alte ID
  schon vergeben (z. B. durch das neue Entwicklerkonto), bekommt das Konto eine neue ID.
- Alte Passwörter funktionieren weiter. Beim ersten Login rechnet der Server sie automatisch in
  das neue Format um.
- Entwickler aus der alten Datenbank werden wieder Entwickler (`is_staff`, `is_superuser`).
- Das Testkonto `test/test` wird nie übernommen.
- Gibt es Name oder E-Mail schon bei einem anderen Konto (zum Beispiel, weil sich jemand auf dem
  neuen Server schon registriert hat), wird das alte Konto **übersprungen** und in der Ausgabe
  genannt. Nichts wird überschrieben. Deshalb den Import direkt nach der Erstinstallation machen.

### 4. Prüfen

1. Die letzte Zeile der Ausgabe zeigt, wie viele Konten jetzt in der Datenbank sind. Die Zahl mit
   der Anzahl der Einträge in `accounts-backup.json` vergleichen (plus Entwicklerkonto).
2. Im Spiel mit einem alten Konto anmelden (Benutzername **oder** E-Mail).
3. Optional unter `https://<DOMAIN>/admin/` mit dem Entwicklerkonto anmelden und unter
   **Konten** nachsehen.

### 5. Aufräumen bei Render und GitHub

1. Den alten Dienst bei Render löschen, sobald der Import geklappt hat.
2. Auf GitHub unter **Settings → Developer settings → Fine-grained tokens** den Backup-Token des
   alten Servers löschen.
3. Das private Backup-Repo noch ein paar Wochen als Notfall-Kopie behalten, danach löschen.
4. Die heruntergeladene `accounts-backup.json` auf dem PC löschen.

---

## Google-Anmeldung aktivieren

1. In der Google Cloud Console einen OAuth-Client vom Typ **Webanwendung**
   anlegen und die Anmeldeseite konfigurieren.
2. Als autorisierten JavaScript-Ursprung die HTTPS-Adresse des Spiels
   eintragen, zum Beispiel `https://63-183-198-23.sslip.io` (bzw. die spätere eigene Domain).
3. Auf dem Server in `/opt/westbummeln/.env` `GOOGLE_CLIENT_ID` mit der Client-ID setzen und in
   `/opt/westbummeln` `docker compose up -d` ausführen. Ein Client-Secret ist nicht nötig.
4. Wenn die Google-App im Testmodus ist, die gewünschten Google-Konten als
   Testnutzer eintragen. Anschließend im Browser den Google-Button prüfen.

Google-Spieler erhalten einen automatisch erzeugten Funknamen. Ein Google-Konto
wird erst bei der ersten erfolgreichen Anmeldung im Spiel angelegt.

## Eigenes Entwicklerkonto

Auf dem Server in `/opt/westbummeln/.env` die Variablen `DEVELOPER_USERNAME` und
`DEVELOPER_PASSWORD` setzen (am besten schon bei der Erstinstallation).
Wähle einen freien Benutzernamen und ein eigenes Passwort mit 16–128 Zeichen.
Der Server legt das Konto bei jedem Start an, falls es noch fehlt
(`python manage.py bootstrap_accounts`). Melde dich über das normale
Anmeldeformular an. Die Entwicklerübersicht erscheint direkt darunter. Das
Entwicklerkonto darf sich auch unter `/admin/` anmelden.

Ein bereits vorhandenes normales Konto wird nicht zum Entwicklerkonto.
Bei einer Namenskollision startet der Dienst mit einer Fehlermeldung.
Die Variablen dienen der Ersteinrichtung. Ein später geänderter Wert setzt das
Passwort eines bestehenden Entwicklerkontos nicht zurück.

Im Spiel kannst du mit dem Entwicklerkonto über **Besetzte Leitstelle
übernehmen** die Leitstellenrolle übernehmen. Der bisherige
Leitstellenspieler bleibt im Raum und kann ein Fahrzeug wählen. Die
Übergabe erscheint im Funkprotokoll. Wenn du gerade ein Fahrzeug führst,
musst du es zuerst regulär verlassen.

## E-Mail-Adresse und Testkonto

Beim Erstellen eines Kontos werden Benutzername, E-Mail-Adresse und Passwort
gespeichert (Passwort nur als scrypt-Hash). Benutzername und E-Mail-Adresse sind
eindeutig, beim Namen zählt Groß-/Kleinschreibung nicht. Anmelden kann man sich
mit Benutzername **oder** E-Mail-Adresse.

Testkonto: Benutzername `test`, Passwort `test`. Es wird lokal mit
`python manage.py bootstrap_accounts` angelegt. Auf dem Server nur, wenn die Variable
`CREATE_TEST_ACCOUNT=1` gesetzt ist. Danach wieder entfernen, denn ein Konto mit
so einem Passwort darf nicht dauerhaft öffentlich erreichbar sein. Ohne die
Variable löscht der Server beim Start ein vorhandenes Testkonto.

## Anmeldung und Sitzungen

Die Anmeldung läuft über Django-Sitzungen (Cookie `sessionid`, `HttpOnly`,
`SameSite=Lax`, auf dem Server nur über HTTPS) und gilt 7 Tage. Alle Formulare und
Spielaktionen sind mit Djangos CSRF-Schutz gesichert.
