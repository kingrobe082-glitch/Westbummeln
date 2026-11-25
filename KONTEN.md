# Westbummeln-Konten

Benutzername und Passwort funktionieren nach dem Start von `python server.py`.
Für den Beitritt zu einem Spielraum ist ein Konto erforderlich.

## Google auf Render aktivieren

1. In der Google Cloud Console einen OAuth-Client vom Typ **Webanwendung**
   anlegen und die Anmeldeseite konfigurieren.
2. Als autorisierten JavaScript-Ursprung die HTTPS-Adresse des Spiels
   eintragen, zum Beispiel `https://westbummeln-multiplayer.onrender.com`.
3. Auf Render die Umgebungsvariable `GOOGLE_CLIENT_ID` mit der Client-ID
   setzen und neu deployen. Der Build installiert die Abhängigkeiten aus
   `requirements.txt`. Für diesen Anmeldeablauf ist kein Client-Secret nötig.
4. Wenn die Google-App im Testmodus ist, die gewünschten Google-Konten als
   Testnutzer eintragen. Anschließend im Browser den Google-Button prüfen.

Google-Spieler erhalten einen automatisch erzeugten Funknamen. Ein Google-Konto
wird erst bei der ersten erfolgreichen Anmeldung im Spiel angelegt.

## Kontodaten auf Render behalten

Die Konten liegen standardmäßig in `accounts.sqlite3` neben dem Servercode.
Der Render-Free-Dienst hat keinen persistenten Datenträger. Für dauerhafte
Konten einen Render-Dienst mit persistentem Datenträger einsetzen und
`ACCOUNT_DB_PATH` z. B. auf `/var/data/accounts.sqlite3` setzen, sofern der
Datenträger unter `/var/data` eingehängt ist. Die Datenbank ist für eine einzelne
Serverinstanz vorgesehen.


## Eigenes Entwicklerkonto

Auf Render die geheimen Umgebungsvariablen `DEVELOPER_USERNAME` und
`DEVELOPER_PASSWORD` für den Dienst setzen, bevor du die Version veröffentlichst.
Wähle einen freien Benutzernamen und ein eigenes Passwort mit 16–128 Zeichen.
Der Server legt das Konto beim ersten Start an. Melde dich über das normale
Anmeldeformular an. Die Entwicklerübersicht erscheint direkt darunter.

Ein bereits vorhandenes normales Konto wird nicht zum Entwicklerkonto.
Bei einer Namenskollision startet der Dienst mit einer Fehlermeldung.
Die Variablen dienen der Ersteinrichtung. Ein später geänderter Wert setzt das
Passwort eines bestehenden Entwicklerkontos nicht zurück. Für lokale Tests
kannst du dieselben Variablen vor dem Start des Servers setzen.

Im Spiel kannst du mit dem Entwicklerkonto über **Besetzte Leitstelle
übernehmen** die Leitstellenrolle übernehmen. Der bisherige
Leitstellenspieler bleibt im Raum und kann ein Fahrzeug wählen. Die
Übergabe erscheint im Funkprotokoll. Wenn du gerade ein Fahrzeug führst,
musst du es zuerst regulär verlassen.

## E-Mail-Adresse und Testkonto

Beim Erstellen eines Kontos werden Benutzername, E-Mail-Adresse und Passwort
gespeichert (Passwort nur als scrypt-Hash). Die E-Mail-Adresse muss eindeutig
sein. Anmelden kann man sich mit Benutzername **oder** E-Mail-Adresse. Alte
Konten ohne E-Mail funktionieren weiter; die Datenbank wird automatisch erweitert.

Testkonto: Benutzername `test`, Passwort `test`. Es wird beim lokalen Start von
`python server.py` automatisch angelegt. Auf Render nur, wenn die Variable
`CREATE_TEST_ACCOUNT=1` gesetzt ist. Danach wieder entfernen, denn ein Konto mit
so einem Passwort darf nicht dauerhaft öffentlich erreichbar sein.

## Automatisches Backup auf GitHub (kostenlos, für Render Free)

Der Server sichert die Konten nach jeder Registrierung in ein **privates**
GitHub-Repo und holt sie beim Start zurück, wenn die Datenbank leer ist.

1. Auf GitHub ein neues **privates** Repo anlegen (z. B. `westbummeln-backup`),
   mit einer README, damit der Branch `main` existiert.
2. Unter Settings → Developer settings → Fine-grained tokens ein Token nur für
   dieses Repo erstellen, Berechtigung **Contents: Read and write**.
3. Auf Render die Variablen `BACKUP_GITHUB_TOKEN` (Token) und
   `BACKUP_GITHUB_REPO` (z. B. `meinname/westbummeln-backup`) setzen, neu deployen.

Im Log erscheint „Backup: N Konten wiederhergestellt“. Das Repo enthält E-Mails
und Passwort-Hashes, es muss privat bleiben. Nicht gesichert werden angemeldete
Sitzungen (nach einem Neustart melden sich Spieler neu an) und laufende Spiele.

### Was im Render-Log steht (Backup)

| Zeile | Bedeutung |
|---|---|
| `Backup: bereit.` | Zugriff aufs Repo klappt, Sicherung ist aktiv. |
| `Backup: Repo erreichbar, noch keine Sicherung vorhanden.` | Normal beim allerersten Start. |
| `Backup: N Konten wiederhergestellt.` | Nach einem Neustart wurden die Konten zurückgeholt. |
| `Backup: N Konten gesichert.` | Nach einer Registrierung wurde gespeichert. |
| `Backup: KEIN ZUGRIFF auf GitHub. Status 404 ...` | Token oder Repo-Name falsch (GitHub meldet 404, auch wenn der Token keinen Zugriff hat). Variablen prüfen. |
| `Status 401` | Token ungültig oder abgelaufen. |
| `Status 403` | Token darf nicht schreiben: Contents auf Read and write stellen. |
| `Backup: GitHub nicht erreichbar ...` | Kurzer Ausfall beim Start. Es wird nichts überschrieben, der Server versucht es erneut. |

Eine leere Datenbank überschreibt nie eine vorhandene Sicherung.
