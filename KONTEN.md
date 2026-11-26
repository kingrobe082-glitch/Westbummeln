# Westbummeln-Konten

Die Konten liegen in einer **Postgres-Datenbank** bei Render (`westbummeln-db`, Basic-256mb,
ca. 6 $/Monat). Lokal und in den Tests nimmt das Spiel automatisch eine SQLite-Datei
(`db.sqlite3`), wenn keine `DATABASE_URL` gesetzt ist.

Auf Render startet der Dienst absichtlich **nicht**, wenn `DATABASE_URL` fehlt. So kann er nie
unbemerkt mit einer leeren Wegwerf-Datenbank laufen und Konten verlieren. Schlägt ein Deploy
deshalb fehl, läuft bei Render die vorherige Version einfach weiter.

---

## Umzug auf Postgres (einmalig, Schritt für Schritt)

> **Wichtig:** Schritte 1 und 2 **vor** dem Mergen des Django-Umbaus erledigen.
> Alle Spieler werden nach dem Umzug einmal abgemeldet und müssen sich neu anmelden.
> Passwörter bleiben gültig.

### 1. Datenbank anlegen (vor dem Merge)

1. In Render deinen Webdienst `westbummeln-multiplayer` öffnen und unter **Settings** nachsehen,
   in welcher **Region** er läuft (z. B. Oregon oder Frankfurt).
2. Oben **New → Postgres** wählen.
3. **Name:** genau `westbummeln-db` eintippen.
4. **Region:** dieselbe wie beim Webdienst. Das ist wichtig, sonst können sich die beiden intern
   nicht erreichen. Steht in `render.yaml` keine `region`, ist es Oregon.
5. **Instance Type:** **Basic-256mb**. Nicht „Free“ nehmen: Die kostenlose Datenbank wird nach
   30 Tagen gelöscht.
6. **Create Database** klicken und warten, bis oben **Available** steht (ein paar Minuten).

### 2. Datenbank mit dem Webdienst verbinden (vor dem Merge)

1. In der neuen Datenbank auf **Connect** klicken und die **Internal Database URL** kopieren.
2. Im Webdienst **Environment** öffnen und diese Variablen anlegen:
   - `DATABASE_URL` = die eben kopierte Internal Database URL
   - `SECRET_KEY` = eine lange Zufallszeichenkette (Render bietet dafür **Generate** an)
3. **Save Changes** klicken. Der alte Server ignoriert diese Variablen, es passiert also noch nichts.

Wird der Dienst als **Blueprint** verwaltet, übernimmt `render.yaml` diese Verbindung nach dem
Merge ebenfalls. Dann bei **Blueprints** prüfen, dass `westbummeln-db` mit der eben angelegten
Datenbank verknüpft ist und keine zweite angelegt wurde.

### 3. Mergen und Deploy abwarten

Den Pull Request mergen. Render baut die neue Version, legt beim Start die Tabellen an
(`python manage.py migrate`) und startet das Spiel. Im Log steht danach `Booting worker`.
Die Startseite lädt, aber es gibt noch keine alten Konten.

### 4. Alte Konten herunterladen (nach dem Deploy)

1. Auf GitHub dein **privates** Backup-Repo öffnen (z. B. `westbummeln-backup`).
2. Die Datei `accounts-backup.json` öffnen und rechts oben auf **Download raw file** klicken.
3. Erst **nach** dem Deploy herunterladen: Der alte Server sichert bei jeder Registrierung und beim
   Herunterfahren. Dann ist auch das letzte neue Konto dabei.
4. Die Datei gut aufheben und **niemals** ins öffentliche Spiel-Repo legen. Sie enthält E-Mails
   und Passwort-Hashes.

### 5. Alte Konten importieren (vom eigenen PC aus)

Render Free hat keine Shell im Browser. Deshalb läuft der Import einmal auf deinem PC und
schreibt direkt in die Render-Datenbank.

1. In der Datenbank bei Render auf **Connect** klicken und die **External Database URL** kopieren.
2. Auf dem PC im Ordner des Spiel-Repos (aktueller Stand von `main`) eine PowerShell öffnen und
   einmalig die Pakete installieren:

   ```powershell
   python -m pip install -r requirements.txt
   ```

3. Die Datenbank-Adresse nur für dieses Fenster setzen (die Anführungszeichen bleiben stehen):

   ```powershell
   $env:DATABASE_URL = "HIER-DIE-EXTERNAL-DATABASE-URL"
   ```

4. Zuerst einen **Probelauf** machen, der nichts speichert:

   ```powershell
   python manage.py import_legacy_accounts "C:\Pfad\zu\accounts-backup.json" --probelauf
   ```

5. Sieht die Ausgabe gut aus, dann richtig:

   ```powershell
   python manage.py import_legacy_accounts "C:\Pfad\zu\accounts-backup.json"
   ```

Statt der JSON-Datei geht auch eine alte `accounts.sqlite3`. Der Befehl kann gefahrlos mehrmals
laufen. Ein zweiter Lauf meldet „Neu übernommen: 0“ und ändert nichts.

**Was der Import macht:**
- Konten behalten ihre alte ID, Name, E-Mail, Google- und Discord-Verknüpfung.
- Alte Passwörter funktionieren weiter. Beim ersten Login rechnet der Server sie automatisch in
  das neue Format um.
- Entwickler aus der alten Datenbank werden wieder Entwickler (`is_staff`, `is_superuser`).
- Das Testkonto `test/test` wird nie übernommen.
- Gibt es Name oder E-Mail schon bei einem anderen Konto (zum Beispiel, weil sich jemand nach dem
  Deploy schon neu registriert hat), wird das alte Konto **übersprungen** und in der Ausgabe
  genannt. Nichts wird überschrieben. Deshalb den Import direkt nach dem Deploy machen.

### 6. Prüfen

1. Die letzte Zeile der Ausgabe zeigt, wie viele Konten jetzt in der Datenbank sind. Die Zahl mit
   der Anzahl der Einträge in `accounts-backup.json` vergleichen.
2. Im Spiel mit einem alten Konto anmelden (Benutzername **oder** E-Mail).
3. Optional unter `https://westbummeln-multiplayer.onrender.com/admin/` mit dem Entwicklerkonto
   anmelden und unter **Konten** nachsehen.

### 7. Aufräumen

1. Im Webdienst unter **Environment** die Variablen `BACKUP_GITHUB_TOKEN`, `BACKUP_GITHUB_REPO`,
   `BACKUP_GITHUB_BRANCH` und `BACKUP_FILE` löschen (falls vorhanden). Der neue Server benutzt sie
   nicht mehr.
2. Auf GitHub unter **Settings → Developer settings → Fine-grained tokens** den Backup-Token löschen.
3. Das private Backup-Repo noch ein paar Wochen als Notfall-Kopie behalten, danach löschen.
4. Die heruntergeladene `accounts-backup.json` auf dem PC löschen.

Ab jetzt sichert Render die Datenbank selbst. Bezahlte Render-Datenbanken lassen sich auf einen
früheren Zeitpunkt zurücksetzen (Datenbank → **Recovery**).

---

## Google auf Render aktivieren

1. In der Google Cloud Console einen OAuth-Client vom Typ **Webanwendung**
   anlegen und die Anmeldeseite konfigurieren.
2. Als autorisierten JavaScript-Ursprung die HTTPS-Adresse des Spiels
   eintragen, zum Beispiel `https://westbummeln-multiplayer.onrender.com`.
3. Auf Render die Umgebungsvariable `GOOGLE_CLIENT_ID` mit der Client-ID
   setzen und neu deployen. Für diesen Anmeldeablauf ist kein Client-Secret nötig.
4. Wenn die Google-App im Testmodus ist, die gewünschten Google-Konten als
   Testnutzer eintragen. Anschließend im Browser den Google-Button prüfen.

Google-Spieler erhalten einen automatisch erzeugten Funknamen. Ein Google-Konto
wird erst bei der ersten erfolgreichen Anmeldung im Spiel angelegt.

## Eigenes Entwicklerkonto

Auf Render die geheimen Umgebungsvariablen `DEVELOPER_USERNAME` und
`DEVELOPER_PASSWORD` für den Dienst setzen, bevor du die Version veröffentlichst.
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
`python manage.py bootstrap_accounts` angelegt. Auf Render nur, wenn die Variable
`CREATE_TEST_ACCOUNT=1` gesetzt ist. Danach wieder entfernen, denn ein Konto mit
so einem Passwort darf nicht dauerhaft öffentlich erreichbar sein. Ohne die
Variable löscht der Server auf Render beim Start ein vorhandenes Testkonto.

## Anmeldung und Sitzungen

Die Anmeldung läuft über Django-Sitzungen (Cookie `sessionid`, `HttpOnly`,
`SameSite=Lax`, auf Render nur über HTTPS) und gilt 7 Tage. Alle Formulare und
Spielaktionen sind mit Djangos CSRF-Schutz gesichert.
