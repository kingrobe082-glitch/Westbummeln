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

## Erster Admin (früher „Entwicklerkonto“)

Auf dem Server in `/opt/westbummeln/.env` die Variablen `DEVELOPER_USERNAME` und
`DEVELOPER_PASSWORD` setzen (am besten schon bei der Erstinstallation).
Wähle einen freien Benutzernamen und ein eigenes Passwort mit 16–128 Zeichen.
Der Server legt das Konto bei jedem Start an, falls es noch fehlt
(`python manage.py bootstrap_accounts`). Es ist Superuser und damit Admin.
Weitere Moderatoren und Admins ernennst du danach unter `/admin/` (siehe unten).

Ein bereits vorhandenes normales Konto wird nicht zum Admin.
Bei einer Namenskollision startet der Dienst mit einer Fehlermeldung.
Die Variablen dienen der Ersteinrichtung. Ein später geänderter Wert setzt das
Passwort eines bestehenden Kontos nicht zurück. Alte Entwicklerkonten aus der
früheren Datenbank werden beim Import zu Admins.

## Rollen und Moderation

| Rolle | Darf |
|---|---|
| Spieler | spielen |
| Moderator | `/admin/` öffnen, Konten ansehen und suchen, Spieler sperren und entsperren, aktive Räume ansehen, Spieler aus Räumen entfernen, Räume schließen, besetzte Leitstelle übernehmen |
| Admin | alles wie Moderator, außerdem Kontodaten bearbeiten, Rollen vergeben, Moderatoren und Admins sperren, Djangos Änderungsprotokoll sehen |

Rollen sind die Gruppen „Moderator“ und „Admin“; ihre Rechte gleicht der Server bei
jedem `migrate` ab. Rolle ändern: Konto unter `/admin/` öffnen → **Rolle ändern**.
Niemand ändert die eigene Rolle oder sperrt sich selbst. Angemeldete Moderatoren
und Admins sehen auf der Spielseite den Link **Moderation öffnen**.

**Sperren:** Konto öffnen → **Sperren**, Dauer (1 Stunde, 1 Tag, 7 Tage, dauerhaft)
und Grund wählen. Oder in der Kontoliste mehrere Konten auswählen → Aktion
„Ausgewählte Konten sperren …“. Eine Sperre beendet sofort alle Sitzungen und nimmt
den Spieler aus allen Räumen (Fahrzeug und Leitstelle werden frei, die Funkmeldung
nennt keinen Grund; besitzt er einen Raum, verwaltet ihn ein anderer Spieler).
Anmelden mit Passwort, Google oder Discord zeigt „Dein Konto ist gesperrt bis …“.
Den Grund sieht nur die Moderation. **Sperre aufheben** beendet sie vorzeitig.

**Aktive Räume** zeigt alle Räume mit Spielern. **Entfernen** wirft einen Spieler
hinaus (er darf wieder beitreten), **Raum schließen** löscht den Raum samt Spielstand.

**Moderationsprotokoll** listet jede Sperre, Entsperrung, jeden Rauswurf, jede
Raumschließung und Rollenänderung mit Zeit, Akteur und Ziel, filterbar nach Aktion,
Datum und Akteur. Andere Änderungen im Admin stehen unter „Logeinträge“ (nur Admins).

Schreibende Anfragen an `/admin/` sind auf 60 pro Minute und IP begrenzt
(`RATE_LIMIT_MODERATION`).

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
