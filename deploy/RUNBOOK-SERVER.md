# Runbook: Westbummeln-Server (AWS EC2)

Ein einzelner Server trägt den ganzen Stack: Caddy (HTTPS), Django (gunicorn, **genau 1 Worker** –
der Spielzustand liegt im Speicher), Postgres und ein Backup-Container. Images baut GitHub Actions,
schiebt sie nach `ghcr.io/kingrobe082-glitch/westbummeln` und deployt per SSH als Benutzer `deploy`.

Dieses Dokument beschreibt nur den **Host** (Betriebssystem, Docker, Firewall, Zugang).
Compose-Datei, Caddyfile und `remote-deploy.sh` liegen ebenfalls in `deploy/`, der Release-Ablauf in
`.github/workflows/release.yml`.

## Eckdaten

| | |
|---|---|
| Instanz | AWS EC2 t3.micro, eu-central-1 (Frankfurt), 2 vCPU, ~900 MB RAM, 28 GB Disk |
| System | Ubuntu 26.04 LTS („resolute“) |
| Domain | `planspiel.7z2.de` (A-Record → `63.184.64.49`, kein AAAA-Record) |
| Öffentliche IP | `63.184.64.49` (Elastic IP, fest) |
| Hostname / Zeitzone | `westbummeln` / `Europe/Berlin` |
| Admin-Zugang | `ssh -i "C:\Users\Lars\Downloads\lars-devvi.pem" ubuntu@63.184.64.49` (sudo ohne Passwort) |
| Deploy-Zugang | `ssh -i "C:\Users\Lars\.ssh\westbummeln_deploy" deploy@63.184.64.49` (kein sudo, Gruppe docker) |
| App-Ordner | `/opt/westbummeln` (Besitzer `deploy`, 750), darin `backups/` |

## Stand 26.11.2026

- [x] `host-setup.sh` gelaufen (Zweitlauf ohne Änderungen): Docker 29.10.1 aus dem offiziellen Repo,
      Compose v5.8.0, Swap 2 GB, ufw aktiv, sshd gehärtet, fail2ban aktiv, Hostname/Zeitzone gesetzt
- [x] Neue Verbindungen als `ubuntu` und `deploy` geprüft, Passwort-Login abgelehnt,
      `docker run --rm hello-world` als `deploy` ok, scp als `deploy` ok, `deploy` hat kein sudo
- [x] Von außen erreichbar: 80/tcp und 443/tcp (Probe-Container). 443/udp nicht getestet.
- [x] Domain `planspiel.7z2.de` zeigt auf den Server: `curl http://planspiel.7z2.de/` erreicht den Probe-Container
- [x] GitHub-Secrets `DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_SSH_KEY`, `DEPLOY_KNOWN_HOSTS` gesetzt
- [ ] Security Group: prüfen, dass 22/tcp für GitHub Actions offen ist (0.0.0.0/0) und 443/udp erlaubt ist
- [ ] Compose-Stack ausrollen (Release-Pipeline)

## Was `deploy/host-setup.sh` einrichtet

Das Skript ist idempotent: erneutes Ausführen bringt den Server wieder auf den Sollzustand und
ändert nichts, was schon stimmt.

1. **Hostname** `westbummeln` (+ `/etc/hosts`, `preserve_hostname: true` für cloud-init, sonst setzt
   cloud-init beim Boot wieder `ip-172-…`), **Zeitzone** Europe/Berlin.
2. `apt-get full-upgrade`, dazu `unattended-upgrades` (nur Sicherheitsupdates von Ubuntu,
   **automatischer Neustart um 04:00** deutscher Zeit, wenn ein Update ihn verlangt).
3. **Swap 2 GB** in `/swapfile` (fstab), `vm.swappiness=10`, ein paar Netzwerk-sysctls
   (`/etc/sysctl.d/99-westbummeln.conf`).
4. **Docker Engine + Compose-Plugin** aus dem offiziellen Docker-apt-Repo (`download.docker.com`,
   Suite `resolute` – existiert für 26.04). Fallback im Skript: gibt es für die Ubuntu-Version kein
   Docker-Repo, werden Ubuntus `docker.io` + `docker-compose-v2` installiert.
   `/etc/docker/daemon.json`: Log-Rotation (json-file, 20 MB × 5 Dateien pro Container) und
   `live-restore: true` – Container laufen weiter, wenn der Docker-Daemon neu startet
   (z. B. bei einem Docker-Update), der Spielzustand bleibt also erhalten.
5. **Benutzer `deploy`**: kein gültiges Passwort, Gruppe `docker`, kein sudo. Login nur mit dem
   Deploy-Schlüssel, eingetragen in `~deploy/.ssh/authorized_keys` mit der Option `restrict`
   (kein Port-/Agent-/X11-Forwarding, kein PTY; Befehle und scp/sftp funktionieren).
6. `/opt/westbummeln` und `/opt/westbummeln/backups` (deploy:deploy, 750).
7. **ufw**: eingehend alles verboten außer 22/tcp, 80/tcp, 443/tcp, 443/udp (HTTP/3).
   Das Skript aktiviert ufw nur, wenn die Regel für 22 nachweislich drinsteht.
8. **sshd** per Drop-in `/etc/ssh/sshd_config.d/10-westbummeln.conf`: keine Passwörter, kein
   keyboard-interactive, kein Root-Login, `MaxAuthTries 4`. Vor dem Reload `sshd -t`; schlägt der
   Test fehl, nimmt das Skript das Drop-in zurück. Reload trennt bestehende Verbindungen nicht.
9. **fail2ban** für sshd (systemd-Journal, 5 Fehlversuche in 10 min → 1 h Sperre).

## Ausführen (Ersteinrichtung oder erneut)

Von Lars' PC (Git-Bash oder PowerShell), im Repo-Ordner:

```bash
scp -i "C:\Users\Lars\Downloads\lars-devvi.pem" deploy/host-setup.sh "C:\Users\Lars\.ssh\westbummeln_deploy.pub" ubuntu@63.184.64.49:/tmp/
ssh -i "C:\Users\Lars\Downloads\lars-devvi.pem" ubuntu@63.184.64.49 "sudo bash /tmp/host-setup.sh /tmp/westbummeln_deploy.pub"
```

Ohne das zweite Argument bleibt `authorized_keys` von `deploy` unverändert.
Meldet das Skript am Ende „Neustart erforderlich“: `sudo reboot` (vorher prüfen, dass kein Spiel läuft).

### Aussperr-Schutz bei Änderungen an ufw/sshd

Vor jeder Änderung an Firewall oder sshd einen Totmannschalter setzen, der nach 15 Minuten alles
zurücknimmt, und ihn erst abbrechen, wenn **neue** Verbindungen als `ubuntu` und `deploy` klappen:

```bash
sudo systemd-run --unit=wb-rollback --on-active=15min /bin/sh -c \
  "ufw --force disable; rm -f /etc/ssh/sshd_config.d/10-westbummeln.conf; systemctl try-reload-or-restart ssh.service"
# … Änderung durchführen, in einem ZWEITEN Fenster neu einloggen (ubuntu und deploy) …
sudo systemctl stop wb-rollback.timer
```

Letzter Ausweg, wenn trotzdem kein SSH mehr geht: AWS-Konsole → EC2 → Instanz → *Connect* →
*EC2 Serial Console* (muss im Konto einmal aktiviert sein) oder Instanz stoppen, Root-Volume an
eine Hilfsinstanz hängen und `/etc/ssh/sshd_config.d/10-westbummeln.conf` bzw. `/etc/ufw/ufw.conf`
(`ENABLED=no`) korrigieren.

## Prüfen

```bash
sudo ufw status verbose            # 22/tcp, 80/tcp, 443/tcp, 443/udp ALLOW, sonst deny
sudo sshd -t && sudo sshd -T | grep -Ei '^(passwordauthentication|kbdinteractiveauthentication|permitrootlogin) '
swapon --show                       # /swapfile 2G
sysctl vm.swappiness                # 10
sudo fail2ban-client status sshd
systemctl is-active docker unattended-upgrades fail2ban
cat /etc/docker/daemon.json
```

Als `deploy` (vom PC aus):

```bash
ssh -i "C:\Users\Lars\.ssh\westbummeln_deploy" deploy@63.184.64.49 "docker run --rm hello-world"
```

## Deploy-Schlüssel und GitHub-Secrets

- Schlüsselpaar: `C:\Users\Lars\.ssh\westbummeln_deploy` (privat, ohne Passphrase, weil GitHub Actions
  ihn nutzt) und `…\westbummeln_deploy.pub`. **Der private Schlüssel gehört nie ins Repo, in einen Chat
  oder in ein Log.**
- Secrets im Repo `kingrobe082-glitch/Westbummeln` (Settings → Secrets and variables → Actions):

  | Secret | Wert |
  |---|---|
  | `DEPLOY_HOST` | `63.184.64.49` |
  | `DEPLOY_USER` | `deploy` |
  | `DEPLOY_SSH_KEY` | Inhalt von `C:\Users\Lars\.ssh\westbummeln_deploy` (komplett, inkl. BEGIN/END-Zeilen) |
  | `DEPLOY_KNOWN_HOSTS` | Ausgabe von `ssh-keyscan -t ed25519 63.184.64.49` |

  Alle vier sind seit 26.11.2026 gesetzt (mit Lars' Schreibrechten, Admin war nicht nötig).
  Neu setzen per CLI, ohne dass der Schlüssel im Terminal erscheint:

  ```bash
  gh secret set DEPLOY_HOST -R kingrobe082-glitch/Westbummeln --body 63.184.64.49
  gh secret set DEPLOY_USER -R kingrobe082-glitch/Westbummeln --body deploy
  gh secret set DEPLOY_SSH_KEY -R kingrobe082-glitch/Westbummeln < ~/.ssh/westbummeln_deploy
  ssh-keyscan -t ed25519 63.184.64.49 > /tmp/wb_known_hosts
  gh secret set DEPLOY_KNOWN_HOSTS -R kingrobe082-glitch/Westbummeln < /tmp/wb_known_hosts
  ```

- **Schlüssel tauschen**: neues Paar erzeugen, `host-setup.sh` mit dem neuen `.pub` laufen lassen
  (fügt ihn hinzu), Secret `DEPLOY_SSH_KEY` ersetzen, einen Deploy testen, dann die alte Zeile
  aus `/home/deploy/.ssh/authorized_keys` löschen.
- **Feste Adresse**: `63.184.64.49` ist eine **Elastic IP** (seit 26.11.2026) und bleibt bei
  Stop/Start gleich. Ohne Elastic IP bekäme die Instanz bei jedem Stop/Start eine neue öffentliche
  Adresse (so ist die erste Adresse `63.183.198.23` verloren gegangen). Wird die Elastic IP je
  gelöst oder die Instanz ersetzt: `DEPLOY_HOST` und `DEPLOY_KNOWN_HOSTS` neu setzen und den
  DNS-Eintrag anpassen.

## AWS Security Group

Die Security Group der Instanz muss eingehend erlauben (ufw auf dem Server ist die zweite Schicht):

| Typ | Port | Quelle |
|---|---|---|
| SSH | 22/tcp | 0.0.0.0/0 (GitHub-Actions-Runner haben wechselnde IPs) |
| HTTP | 80/tcp | 0.0.0.0/0 und ::/0 (Caddy braucht 80 für die Let's-Encrypt-Prüfung und die Umleitung) |
| HTTPS | 443/tcp | 0.0.0.0/0 und ::/0 |
| HTTP/3 | 443/udp | 0.0.0.0/0 und ::/0 |

Test, ob 80 von außen ankommt (danach Container wieder weg):

```bash
sudo docker run --rm -d -p 80:80 --name probe caddy:2-alpine caddy respond --listen :80 "ok"
# vom PC:  curl http://63.184.64.49/   → ok
#          curl http://planspiel.7z2.de/   → ok   (prüft zusätzlich den DNS-Eintrag)
sudo docker rm -f probe
```

## Wichtig zu wissen

- **Docker umgeht ufw für veröffentlichte Ports.** Ein `ports: - "5432:5432"` in der Compose-Datei
  wäre trotz ufw aus dem Internet erreichbar (nur die Security Group schützt dann noch). Postgres und
  Django deshalb **ohne** `ports:` betreiben, nur Caddy veröffentlicht 80/443. Muss doch einmal etwas
  lokal veröffentlicht werden: `127.0.0.1:PORT:PORT`.
- **Neustart um 04:00**: Nach Sicherheitsupdates, die einen Neustart verlangen, startet der Server
  nachts neu. Der Spielzustand im Speicher geht dabei verloren; die Container brauchen
  `restart: unless-stopped`, damit sie danach von selbst wieder hochkommen.
- **RAM ist knapp** (~900 MB). Swap fängt Spitzen ab, ersetzt aber keinen Speicher. Speicher prüfen
  mit `free -m` und `docker stats --no-stream`.
- Docker-Updates kommen nicht über unattended-upgrades (das spielt nur Ubuntu-Sicherheitsupdates ein).
  Docker von Hand aktualisieren: `sudo apt-get update && sudo apt-get install --only-upgrade docker-ce docker-ce-cli containerd.io docker-compose-plugin docker-buildx-plugin`
  – dank `live-restore` laufen die Container dabei weiter.
