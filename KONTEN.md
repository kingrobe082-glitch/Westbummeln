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

Konten vom früheren Render-Server gibt es nicht zu übernehmen (dort lag nur eine flüchtige
SQLite-Datei ohne Sicherung). Der neue Server startet leer, Spieler registrieren sich neu.

---

## Google-Anmeldung aktivieren

1. In der Google Cloud Console einen OAuth-Client vom Typ **Webanwendung**
   anlegen und die Anmeldeseite konfigurieren.
2. Als autorisierten JavaScript-Ursprung die HTTPS-Adresse des Spiels
   eintragen: `https://planspiel.7z2.de`.
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
