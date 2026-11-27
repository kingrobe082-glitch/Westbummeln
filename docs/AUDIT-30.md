# Westbummeln – 30 Änderungen (Audit 27.11.2026, Stand origin/main 9333e11)

## A – Muss (Fehler/Risiko)

1. Serverfehler unsichtbar – `/api` und `/account` fangen jede Ausnahme ab und antworten „Serverfehler“, ohne irgendetwas zu loggen → im `except Exception` `logger.exception(...)` ergänzen, damit Tracebacks in `docker compose logs web` landen (Aufwand: S; Beleg: game/views.py:58-59, accounts/views.py:68-69)
2. Offene Einsätze unbegrenzt – eine Leitstelle kann per Skript beliebig viele offene Einsätze anlegen, jeder Poll serialisiert sie unter der globalen Sperre und bremst damit alle Räume → Obergrenze (z. B. 25 offene Einsätze pro Raum) in `_incident` plus Test (Aufwand: S; Beleg: game/engine.py:576-586, game/engine.py:295-298, game/views.py:43-53)
3. Kein Alarm bei Ausfall – `/healthz` wird nur am Ende eines Deploys geprüft, fällt der Server nachts aus, merkt es niemand → externen Uptime-Monitor (z. B. UptimeRobot/healthchecks.io) auf https://planspiel.7z2.de/healthz mit Mail/Push an Lars, dazu Ping nach jeder erfolgreichen Sicherung (Aufwand: S; Beleg: deploy/RELEASE.md:34, kein Monitoring in deploy/)
4. Container außer web werden nie aktualisiert – `remote-deploy.sh` zieht nur das web-Image, Caddy, Postgres und das Backup-Image bleiben auf dem Stand der Erstinstallation (keine Sicherheitsupdates) → in remote-deploy `docker compose pull` für alle Dienste oder wöchentlicher Update-Job, Versionen in der Compose-Datei festpinnen (Aufwand: S; Beleg: deploy/remote-deploy.sh:66, deploy/docker-compose.prod.yml caddy:2-alpine/postgres:17-alpine)
5. API-Limit reicht nur für ~3 Spieler pro Internetanschluss – 240 Anfragen/min pro IP, ein Spieler braucht ~75/min, ab dem 4. Spieler im selben WLAN kommen 429-Fehler und „Verbindung unterbrochen“ → Limit pro Konto statt pro IP oder auf ~1200/min anheben (Aufwand: S; Beleg: westbummeln/settings.py:159-165; rechnerisch, live unbestätigt)
6. Backups liegen auf derselben Platte – tägliche Sicherungen nur in `/opt/westbummeln/backups` auf der EBS-Platte des Servers, Kopie nur „ab und zu“ per Hand → AWS Data Lifecycle Manager (tägliche EBS-Snapshots) plus nächtliche Kopie der Dumps nach S3 in einer anderen Region (Aufwand: M; Beleg: deploy/docker-compose.prod.yml:126, deploy/RUNBOOK.md:154)
7. Jeder Merge beendet alle laufenden Spiele – Release läuft automatisch nach jedem Merge auf main, der Neustart von web löscht alle Räume im Speicher und wirft Spieler mit „Raum nicht gefunden“ raus → Räume beim Herunterfahren als JSON sichern und beim Start laden (Räume sind reine dicts), mindestens Deploy-Hinweis im Spiel 2 min vorher (Aufwand: M; Beleg: deploy/RUNBOOK.md:37, deploy/remote-deploy.sh:109, .github/workflows/release.yml:11-14)
8. Deploy-Schlüssel ist faktisch root – Benutzer `deploy` ist in der Gruppe docker, `authorized_keys` erlaubt mit `restrict` jeden Befehl, SSH ist für 0.0.0.0/0 offen; wer das GitHub-Secret hat, hat den Server → in `authorized_keys` `command="…/deploy-wrapper.sh"` erzwingen, der nur Upload + `remote-deploy.sh` zulässt (Aufwand: M; Beleg: deploy/RUNBOOK-SERVER.md:21, :54, :151)
9. Wiederherstellung nie auf dem Server geprobt – Restore ist nur lokal getestet, „Server komplett weg“ ist ungeübt → einmal neue t3.micro aus Runbook + Backup aufsetzen, Dauer und Stolpersteine ins Runbook, dann halbjährlich wiederholen (Aufwand: M; Beleg: deploy/RUNBOOK.md:165, :211-212)

## B – Sollte (spürbar besser)

10. Funkzeiten eine Stunde falsch – Funkprotokoll zeigt UTC (live 23:12 statt 00:12 Ortszeit) → Zeitstempel mit `zoneinfo('Europe/Berlin')` bilden (Aufwand: S; Beleg: game/engine.py:93, westbummeln/settings.py:208, live-Test 27.11.)
11. Python-Fehlertexte beim Spieler – ungültige Zahlen liefern „invalid literal for int() with base 10: 'abc'“, KeyError/TypeError werden roh durchgereicht → Zahlen über eine Hilfsfunktion mit deutscher Meldung parsen, bei KeyError/TypeError nur „Ungültige Anfrage“ antworten (Aufwand: S; Beleg: game/engine.py:404, :435, :565, game/views.py:56-57, live-Test)
12. KI legt sofort los, bevor Mitspieler da sind – im frisch erstellten Raum erzeugt die KI in der ersten Sekunde einen Einsatz und schickt ein Fahrzeug los, der zweite Spieler bekommt beim Übernehmen „Fahrzeug ist unterwegs“ → `ai_last` beim Anlegen auf jetzt setzen, ersten KI-Einsatz frühestens nach 45 s (Aufwand: S; Beleg: game/engine.py:78, :200, live-Test: WB-1-HLF20 1 s nach Raumerstellung unterwegs)
13. Unklare Meldungen bei Neustart/Ausfall – `api()` ruft `res.json()` ohne Absicherung auf, bei leerer 502-Antwort steht „Unexpected end of JSON input“ im Hinweis → JSON-Lesen absichern und „Server startet neu – gleich wieder versuchen“ anzeigen (Aufwand: S; Beleg: static/js/game.js:53)
14. Screenreader und Beschriftungen – Stichwort, Einsatzort, Fahrzeugsuche, Filter und Funkspruch haben nur Platzhalter statt Label, das Funklog (`aria-live`) wird bei jeder Änderung komplett neu geschrieben → `aria-label` ergänzen, im Log nur neue Einträge anhängen (Aufwand: S; Beleg: templates/index.html:55-63, static/js/game.js:121)
15. JS und CSS kaum wartbar – Kernlogik steht in Einzeilern bis 559 Zeichen (game.js), CSS in zwei Riesenzeilen → nach dem Merge der laufenden Sessions einmal mit Prettier formatieren und ESLint in die CI (Aufwand: S; Beleg: static/js/game.js:53, static/css/app.css:1, :4)
16. Raum-Limit leicht ausschöpfbar – 200 Räume für alle, 2 pro Konto, Konten kostenlos (5/h pro IP); wer Räume anlegt und geht, blockiert sie 30 min, dann heißt es „alle Räume belegt“ → Raumerstellung zusätzlich pro IP begrenzen und leere Räume ohne jemals zweiten Spieler nach 5 min löschen (Aufwand: S; Beleg: game/rooms.py:92-99, westbummeln/settings.py:230; unbestätigt)
17. Im Hintergrund nach 30 s raus – gesperrtes Handy oder gedrosselter Tab pollt nicht, nach 30 s ist der Spieler entfernt und sein Fahrzeug weg → Timeout für GF auf 90–120 s und beim Wiederbeitritt Rolle/Fahrzeug zurückgeben (Aufwand: M; Beleg: game/engine.py:45, :114-130, static/js/game.js:141; unbestätigt auf echtem Handy)
18. Poll schickt immer alles – jede Abfrage liefert den vollen Spielstand (live 5,7–6,4 KB alle 1,5 s ≈ 14 MB/h pro Spieler), auch wenn sich nichts geändert hat → Client schickt `rev`, Server antwortet bei gleichem Stand nur `{unchanged:true}` (Aufwand: M; Beleg: game/engine.py:394-395, live-Test)
19. Neue Spieler verstehen das Spiel nicht – außer je einem Satz gibt es keine Erklärung zu Rollen, FMS-Status 1–6, Alarmierung und wie ein Einsatz endet → aufklappbare Kurzanleitung „So spielst du“ je Rolle (3–5 Schritte) im Raum (Aufwand: M; Beleg: templates/index.html Startbildschirm/Rollenwahl)
20. Kein Browser-Test – 211 Python-Tests, aber nichts prüft, ob Seite und JS funktionieren → Playwright-Smoke-Test in der CI (registrieren, Raum erstellen, Leitstelle, Einsatz, Alarm) (Aufwand: M; Beleg: tests/ enthält nur Python, .github/workflows/ci.yml:52)
21. Admin-Login ohne zweiten Faktor – `/admin/` ist öffentlich erreichbar, Moderator- und Admin-Konten schützt nur ein Passwort → TOTP (django-otp) für Staff oder `/admin/` in Caddy auf bekannte IPs beschränken (Aufwand: M; Beleg: live https://planspiel.7z2.de/admin/ → 302 Login, requirements.txt ohne OTP)

## C – Kann (nett)

22. HSTS steht noch auf 1 Tag – laut Kommentar Übergangswert → auf `max-age=31536000` erhöhen (Aufwand: S; Beleg: deploy/Caddyfile:24, live-Header)
23. Datenschutzseite nennt falsche Loggröße – Seite sagt 5 × 20 MB, Compose setzt 3 × 10 MB → Text angleichen (Aufwand: S; Beleg: templates/datenschutz.html:57, deploy/docker-compose.prod.yml:37)
24. Render-Reste im Code – `RENDER`, `RENDER_EXTERNAL_HOSTNAME`, `RENDER_EXTERNAL_URL` und Render-Tests leben weiter → nach Abschalten des Altdienstes entfernen (Aufwand: S; Beleg: westbummeln/settings.py:18-19, :41-44, integrations/discord.py:108, tests/test_settings.py:74-80)
25. Verwechselbare Benutzernamen – `\w` erlaubt Unicode-Doppelgänger (kyrillisches „а“), Namen wie „System“ oder „Leitstelle“ sind frei, Groß/Klein-Eindeutigkeit nur im Code statt in der DB → auf ASCII beschränken, reservierte Namen sperren, Unique-Index auf `lower(username)` (Aufwand: S; Beleg: accounts/services.py:21, :59-62)
26. KI-Einsätze vorhersehbar – KI nimmt Orte der Reihe nach und nur 4 Stichworte im Kreis → zufällige Auswahl, mehr Stichworte (Aufwand: S; Beleg: game/engine.py:52, :203-204)
27. Wetter starr – Wechsel alle 150 s in fester Reihenfolge über die Uhrzeit → zufällig/gewichtet mit variabler Dauer (Aufwand: S; Beleg: game/engine.py:263-264)
28. Straßenliste doppelt gepflegt – Auswahl im HTML und `PLACES` im Server müssen von Hand gleich bleiben → Auswahl aus `PLACES` rendern (Aufwand: S; Beleg: templates/index.html select#address, game/engine.py:29-42)
29. Sprachfunk ohne TURN – nur Google-STUN, hinter Mobilfunk/CGNAT kommt oft keine Verbindung zustande → coturn auf dem Server (Port 3478) oder im UI ehrlich darauf hinweisen (Aufwand: M; Beleg: static/js/voice.js:7; unbestätigt)
30. Kein Spielziel – jeder Einsatz endet immer erfolgreich, es gibt keine Wertung → Eskalation bei später Alarmierung und Einsatzbilanz am Ende (Zeit bis Alarm/Ankunft) (Aufwand: L; Beleg: game/engine.py:307-327)

## Top 5 zum sofort Angehen

1. Nr. 1 – Serverfehler loggen (S)
2. Nr. 3 – Uptime-Monitor + Backup-Ping (S)
3. Nr. 6 – Backups außerhalb des Servers (M)
4. Nr. 4 – alle Container-Images aktualisieren (S)
5. Nr. 7 – Spiele überleben Deploys (M)
