# Release und Deploy

Westbummeln läuft als Docker-Compose-Stack (Caddy, Django/gunicorn, Postgres, Backup) auf dem
eigenen Server unter `/opt/westbummeln`. Releases laufen automatisch über GitHub Actions
(`.github/workflows/release.yml`).

## Ablauf

```
Merge auf main ──► CI (ci.yml, Postgres + SQLite) ──► Release (release.yml)
                                                     ├─ vorbereiten: Commit bestimmen, Secrets prüfen
                                                     ├─ build: Image bauen und nach ghcr.io pushen
                                                     └─ deploy: deploy/ kopieren, remote-deploy.sh, Healthcheck
```

1. **CI**: Jeder Push auf `main` startet `ci.yml`. Release startet nur, wenn **beide** Testjobs grün sind.
2. **vorbereiten**: Bestimmt den vollen Commit-SHA und prüft, ob alle Deploy-Secrets gesetzt sind.
   Fehlt eins, bricht der Lauf hier mit einer deutschen Meldung ab, bevor etwas gebaut wird.
3. **build**: Baut das Image aus dem `Dockerfile` im Repo-Root für `linux/amd64` und pusht es als
   - `ghcr.io/kingrobe082-glitch/westbummeln:<voller-sha>`
   - `ghcr.io/kingrobe082-glitch/westbummeln:latest` (nur bei automatischen Releases von `main`)

   Liegt das Image für diesen SHA schon in ghcr.io (z. B. bei einem Rollback), wird der Build übersprungen.
4. **deploy** (immer nur einer gleichzeitig, `concurrency: deploy-production`):
   1. Prüft, ob der Commit noch der neueste auf `main` ist. Wenn nicht, wird übersprungen, weil der neuere Lauf deployt.
   2. Kopiert den Inhalt von `deploy/` aus genau diesem Commit nach `/opt/westbummeln`. `.env` und
      `backups/` werden nie übertragen oder überschrieben.
   3. Meldet den Server mit dem kurzlebigen `GITHUB_TOKEN` des Jobs bei ghcr.io an. Das Token verfällt am Jobende,
      auf dem Server liegt kein dauerhaftes Passwort.
   4. Führt `cd /opt/westbummeln && IMAGE_TAG=<sha> ./remote-deploy.sh` aus. Das Skript zieht das Image,
      startet den Stack neu, prüft die Gesundheit und rollt bei einem Fehler selbst zurück (Exit ≠ 0 lässt den Lauf scheitern).
   5. Meldet den Server wieder bei ghcr.io ab.
   6. Prüft `https://<DEPLOY_DOMAIN>/healthz` von außen. Ohne gesetzte Variable entfällt dieser Schritt.

Den Verlauf siehst du unter **Actions → Release**. Jeder Lauf heißt `Release <sha>`.

### Warum `workflow_run` statt CI als `needs` im selben Workflow?

- `ci.yml` bleibt unverändert und ist die einzige Stelle, an der Tests definiert sind. Es gibt keine
  doppelten CI-Läufe auf `main` und keine zweite Kopie der Testschritte.
- Release startet erst, wenn die **ganze** CI (beide Matrix-Jobs) grün ist.
- Der Release-Workflow läuft immer in der Fassung von `main`. Ein PR kann ihn also nicht verändern
  und mit Schreibrechten ausführen.
- Gegen die bekannten Fallen von `workflow_run` ist abgesichert: Release läuft nur für `event == push` aus diesem Repo
  (nicht für Fork-PRs von einem Branch namens `main`). Gebaut wird explizit `head_sha`, nicht der aktuelle Stand von `main`.
  Ein veralteter Lauf deployt nicht über einen neueren.
- Einschränkung: Der Trigger hängt am Namen `CI`. Wird `name:` in `ci.yml` geändert, muss `release.yml` mitgeändert werden.
  Und `workflow_run` und `workflow_dispatch` greifen erst, wenn `release.yml` auf `main` liegt.

## Manuelles Deploy eines bestimmten Commits

Im Browser: **Actions → Release → Run workflow**, Branch `main` lassen, bei *ref* den Commit eintragen
(voller oder kurzer SHA, Tag oder Branch). Leer heißt: aktueller Stand von `main`.

Mit der GitHub-CLI:

```powershell
gh workflow run release.yml -f ref=<sha>
```

```powershell
gh run watch
```

Manuelle Deploys setzen `latest` nicht um. Mit *rebuild* wird das Image auch dann neu gebaut, wenn es schon existiert.
Ein Commit, der nicht in `main` enthalten ist, wird mit Warnung trotzdem deployt.

## Rollback

**Variante A, über GitHub (empfohlen):** wie oben, mit dem SHA der letzten guten Version.
Das Image liegt schon in ghcr.io und wird nicht neu gebaut. Achtung: Auch `deploy/` (Compose-Datei, Caddyfile,
Skript) wird auf den Stand dieses Commits zurückgesetzt. Die Datenbank wird **nicht** zurückgesetzt. Wenn der
schlechte Release Migrationen enthielt, vorher klären, ob die alte Version mit dem neuen Schema läuft.

Frühere SHAs findest du mit `git log --oneline main` oder unter **Actions → Release** (Laufname).

**Variante B, direkt auf dem Server** (z. B. wenn GitHub Actions nicht geht). Host und Benutzer sind die Werte der Secrets `DEPLOY_HOST` und `DEPLOY_USER`:

```powershell
ssh <DEPLOY_USER>@<DEPLOY_HOST>
```

```bash
cd /opt/westbummeln
IMAGE_TAG=<alter-voller-sha> ./remote-deploy.sh
```

Das klappt sofort, wenn das alte Image noch lokal auf dem Server liegt oder das GHCR-Paket öffentlich ist (siehe unten).
Sonst braucht der Server vorher einen Login, z. B. mit einem eigenen Personal Access Token (Scope `read:packages`), den du
direkt danach mit `docker logout ghcr.io` wieder entfernst.

## Benötigte Secrets und Variablen

Repository-Secrets und -Variablen kann nur jemand mit Admin-Rechten auf dem Repo setzen
(**Settings → Secrets and variables → Actions**).

| Name | Art | Pflicht | Inhalt |
|---|---|---|---|
| `DEPLOY_HOST` | Secret | ja | Öffentliche IP oder Hostname des Servers (der aktuelle Wert steht nur in diesem Secret, nicht im Repo) |
| `DEPLOY_USER` | Secret | ja | SSH-Benutzer, `deploy` |
| `DEPLOY_SSH_KEY` | Secret | ja | Privater SSH-Schlüssel (komplett, inkl. `-----BEGIN OPENSSH PRIVATE KEY-----`). Nur für Deploys, ohne Passphrase. Der öffentliche Teil steht in `~deploy/.ssh/authorized_keys`. |
| `DEPLOY_KNOWN_HOSTS` | Secret | ja | Host-Key-Zeile(n) des Servers für `known_hosts`, z. B. Ausgabe von `ssh-keyscan -t ed25519 <DEPLOY_HOST>`. Fingerprint mit `ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub` auf dem Server abgleichen. Bei einem anderen Port als 22 lautet die Zeile `[host]:port …`. |
| `DEPLOY_DOMAIN` | Variable | nein | Öffentliche Domain ohne `https://`, z. B. `westbummeln.example.de`. Ist sie gesetzt, prüft der Lauf am Ende `https://<domain>/healthz`. |
| `DEPLOY_SSH_PORT` | Variable | nein | SSH-Port, Standard `22` |

Ändert sich die IP des Servers, müssen `DEPLOY_HOST` und `DEPLOY_KNOWN_HOSTS` neu gesetzt werden. Workflow und Doku enthalten bewusst keine IP.

`GITHUB_TOKEN` stellt GitHub automatisch bereit. Der Build-Job hat `packages: write`, der Deploy-Job nur `packages: read`.

Beispiel mit der CLI (als Repo-Admin):

```powershell
gh secret set DEPLOY_SSH_KEY --repo kingrobe082-glitch/Westbummeln < deploy_key
```

```powershell
gh variable set DEPLOY_DOMAIN --repo kingrobe082-glitch/Westbummeln --body westbummeln.example.de
```

### Optional: Freigabe vor jedem Deploy

Wer Deploys vor dem Ausführen bestätigen will, legt als Admin unter **Settings → Environments** ein Environment
`production` mit *Required reviewers* an und ergänzt im Job `deploy` die Zeile `environment: production`.
Die Secrets können dann auch als Environment-Secrets dort liegen.

## GHCR-Paket öffentlich machen (optional)

Beim ersten erfolgreichen Build legt GitHub das Paket `westbummeln` an. Es ist privat und über das Label
`org.opencontainers.image.source` mit diesem Repo verknüpft. Das Repo ist ohnehin öffentlich, das Image enthält keine
Geheimnisse (die liegen nur in `/opt/westbummeln/.env`). Deshalb kann der Repo-Besitzer es öffentlich stellen:

1. github.com/kingrobe082-glitch → **Packages** → `westbummeln` (oder im Repo rechts unter *Packages*).
2. **Package settings** → ganz unten *Danger Zone* → **Change visibility** → **Public** → Paketnamen bestätigen.
3. Unter *Manage Actions access* sollte `Westbummeln` mit Rolle *Write* stehen. Der erste Push aus dem Workflow setzt das automatisch.

Danach kann der Server ohne Login pullen (wichtig für Rollback-Variante B). Der Login im Workflow stört nicht und bleibt drin,
damit es auch mit privatem Paket funktioniert.

## Alte Images

Jeder Release hinterlässt ein Image `:<sha>` in ghcr.io. Das ist gewollt, weil Rollbacks ohne Neubau gehen.
Wenn es zu viele werden, kann man alte Versionen unter **Package settings → Manage versions** löschen.
Behalte mindestens die letzten paar Releases.
