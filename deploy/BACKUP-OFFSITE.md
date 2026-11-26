# Sicherungen außerhalb des Servers

Bisher liegen alle Sicherungen in `/opt/westbummeln/backups` auf derselben Platte wie die
Datenbank. Geht die Platte, die Instanz oder das Konto kaputt, sind Datenbank **und** Sicherungen
weg. Deshalb zwei zusätzliche Ebenen:

| Ebene | Was | Wo | Aufbewahrung | Hilft bei |
|---|---|---|---|---|
| **A. EBS-Snapshots** | ganze Platte des Servers | AWS Frankfurt (getrennt von der Platte gespeichert) | 7 Tage, täglich | Platte kaputt, Server verkonfiguriert, schnell alles zurück |
| **B. Dumps in S3** | Datenbank-Sicherungen (`daily/`, `pre-deploy/`) | S3-Bucket in **Irland** (`eu-west-1`) | 90 Tage, alte Fassungen 30 Tage länger | Server weg, Region Frankfurt gestört, Sicherung überschrieben |

Für B läuft auf dem Server der Container `offsite` (rclone). Er kopiert beim Start und jeden Tag
um 04:00 (eine Stunde nach der täglichen Sicherung) die neuen Dateien nach S3. Er hat **keine
Zugangsschlüssel**: Er nutzt die IAM-Rolle der Instanz, und die darf nur auflisten und hochladen,
nicht lesen und nicht löschen. Solange `S3_BACKUP_BUCKET` in `.env` leer ist, tut er nichts.

## Kosten (grob, pro Monat)

| Posten | Rechnung | Kosten |
|---|---|---|
| EBS-Snapshots, 7 Tage | erster Snapshot ≈ belegte Platte (~6 GB), danach nur Änderungen (Deploys, Logs) ≈ 8–15 GB × 0,054 $ | **0,45–0,80 $** |
| S3-Speicher | Dumps ~50 KB pro Tag, 90 Tage + Fassungen: unter 50 MB | < 0,01 $ |
| S3-Anfragen | ~100 Uploads/Listen pro Monat × 0,005 $/1000 | < 0,01 $ |
| Übertragung Frankfurt → Irland | unter 50 MB × 0,02 $/GB | < 0,01 $ |
| **Summe** | | **unter 1 $ pro Monat** |

Preise laut AWS-Preisliste (Frankfurt/Irland), können sich ändern. Wächst die Datenbank, wachsen
die S3-Kosten mit (1 GB in S3 ≈ 0,023 $ pro Monat). Kontrolle: AWS-Konsole → „Billing and Cost
Management“ → „Bills“.

## Was Lars einmalig in AWS klickt

Vorher: Der PR mit dem Container `offsite` ist gemergt und ausgerollt (`docker compose ps` auf dem
Server zeigt `offsite`). Die Konsole ist hier auf Englisch beschrieben.

### 1. S3-Bucket in Irland anlegen

1. AWS-Konsole → oben in der Suche **S3** → öffnen.
2. Oben rechts die Region auf **Europe (Ireland) eu-west-1** stellen.
3. **Create bucket**.
   - **Bucket type:** General purpose.
   - **Bucket name:** z. B. `westbummeln-backup-` plus 6 zufällige Kleinbuchstaben/Ziffern
     (Namen sind weltweit eindeutig). Namen notieren, er kommt unten dreimal vor.
   - **Object Ownership:** ACLs disabled (Standard lassen).
   - **Block all public access:** Haken **an** (Standard lassen).
   - **Bucket Versioning:** **Enable**.
   - **Default encryption:** **SSE-S3** (Server-side encryption with Amazon S3 managed keys,
     Standard lassen).
   - **Create bucket**.
4. Bucket öffnen → Reiter **Management** → **Create lifecycle rule**:
   - **Lifecycle rule name:** `westbummeln-aufbewahrung`
   - **Choose a rule scope:** „Limit the scope of this rule using one or more filters“ →
     **Prefix:** `westbummeln/`
   - **Lifecycle rule actions:** Haken bei
     - „Expire current versions of objects“ → **Days after object creation: 90**
     - „Permanently delete noncurrent versions of objects“ → **Days after objects become
       noncurrent: 30** (Feld „Number of newer versions to retain“ leer lassen)
     - „Delete expired object delete markers or incomplete multipart uploads“ → nur
       „Delete incomplete multipart uploads“ → **7** Tage
   - **Create rule**.

   Dasselbe als Datei: [`aws/s3-lifecycle.json`](aws/s3-lifecycle.json).

### 2. IAM-Rolle anlegen (nur Hochladen) und an den Server hängen

1. Konsole → **IAM** → links **Roles** → **Create role**.
2. **Trusted entity type:** AWS service. **Use case:** **EC2** → **Next**.
3. Seite „Add permissions“: nichts anhaken → **Next**.
4. **Role name:** `westbummeln-offsite-backup` → **Create role**.
5. Die neue Rolle öffnen → **Add permissions** → **Create inline policy** → oben auf **JSON**.
6. Inhalt von [`aws/iam-policy-offsite-backup.json`](aws/iam-policy-offsite-backup.json)
   hineinkopieren und **beide** `DEIN-BUCKET-NAME` durch den Bucket-Namen ersetzen → **Next**.
7. **Policy name:** `s3-nur-hochladen` → **Create policy**.
8. Konsole → **EC2** → Region **Europe (Frankfurt) eu-central-1** → **Instances** → Instanz
   `i-038a2e99da4da8963` anhaken.
9. **Actions** → **Security** → **Modify IAM role** → `westbummeln-offsite-backup` wählen →
   **Update IAM role**.

Hop-Limit: Container erreichen die Metadaten-Adresse der Instanz (IMDSv2) nur bei
„Metadata response hop limit“ ≥ 2. Am 27.11.2026 geprüft: geht schon (aus dem Container `web`
antwortet IMDSv2, IMDSv1 ist abgeschaltet). Nur falls unten in Schritt 5 „no EC2 IMDS role found“
oder „failed to refresh cached credentials“ steht: Instanz anhaken → **Actions** → **Instance
settings** → **Modify instance metadata options** → **Metadata response hop limit: 2** → **Save**.
„IMDSv2: Required“ so lassen.

### 3. Tägliche Snapshots der Platte (Data Lifecycle Manager)

1. Konsole → **EC2** (Frankfurt) → **Instances** → Instanz anklicken → Reiter **Storage** →
   unter „Block devices“ die **Volume ID** (`vol-…`) anklicken.
2. Volume anhaken → Reiter **Tags** → **Manage tags** → **Add new tag**:
   Key `Backup`, Value `westbummeln` → **Save**.
3. EC2 → links **Elastic Block Store** → **Lifecycle Manager** → **Create lifecycle policy**.
4. **Custom policy** und **EBS snapshot policy** wählen → **Next**.
5. Seite „Specify settings“:
   - **Target resource types:** **Volume**
   - **Target resource tags:** Key `Backup`, Value `westbummeln` → **Add**
   - **Policy description:** `westbummeln täglich, 7 Tage`
   - **IAM role:** **Default role**
   - **Policy status:** **Enabled** → **Next**
6. Seite „Configure schedule“, Schedule 1:
   - **Schedule name:** `taeglich`
   - **Frequency:** **Daily**, **Every:** **24 hours**, **Starting at:** **02:30 UTC**
     (= 03:30/04:30 deutscher Zeit, nach der Datenbank-Sicherung um 03:00)
   - **Retention type:** **Count**, **Keep:** **7**
   - **Tagging:** Haken bei **Copy tags from source**
   - Cross-Region-Copy, Fast Snapshot Restore, Archive: **aus** lassen → **Review policy** →
     **Create policy**.

Snapshots liegen in derselben Region (Frankfurt), aber getrennt von der Platte. Gegen den Ausfall
der ganzen Region hilft Ebene B. Snapshots sind „absturzsicher“ (wie Stecker ziehen): Postgres
startet daraus sauber, das ist der normale Fall.

### 4. Bucket auf dem Server eintragen

Per SSH als `deploy` (siehe [RUNBOOK.md](RUNBOOK.md)):

```bash
cd /opt/westbummeln
nano .env
```

Unten anfügen (Bucket-Name einsetzen), speichern mit Strg+O, Enter, Strg+X:

```
S3_BACKUP_BUCKET=westbummeln-backup-xxxxxx
S3_BACKUP_REGION=eu-west-1
```

Dann den Container neu starten (er kopiert sofort einmal):

```bash
docker compose up -d offsite
```

### 5. Prüfen, ob es klappt

1. Auf dem Server:

   ```bash
   docker compose logs --tail=20 offsite
   ```

   Gut: `Copied (new)` für jede Datei, dann `OK` und `Nächste Kopie um 04:00`.
   Läuft noch keine tägliche Sicherung (`backups/daily/` leer), werden nur `pre-deploy/`-Dateien
   kopiert. Sofort eine Sicherung machen und noch einmal kopieren:

   ```bash
   docker compose exec backup /backup.sh
   docker compose exec offsite sh /offsite-backup.sh once
   ```

2. S3-Konsole → Bucket → Ordner `westbummeln/` → `daily/` und `pre-deploy/` enthalten Dateien mit
   heutigem Datum.
3. Am nächsten Tag: `docker compose ps offsite` zeigt **(healthy)**. „unhealthy“ heißt: seit über
   26 Stunden keine erfolgreiche Kopie → Logs ansehen.
4. Nach dem ersten Snapshot-Termin: EC2 → **Elastic Block Store** → **Snapshots** → ein Snapshot
   mit Beschreibung „Created for policy …“, Status **Completed**. Nach 8 Tagen sind es dauerhaft 7.

### Fehlersuche

| Meldung im Log von `offsite` | Ursache | Abhilfe |
|---|---|---|
| `S3_BACKUP_BUCKET ist leer` | `.env` ohne Bucket | Schritt 4 |
| `no EC2 IMDS role found` / `failed to refresh cached credentials` | Rolle nicht an der Instanz oder Hop-Limit 1 | Schritt 2.8–2.9, Hop-Limit 2 |
| `AccessDenied` bei `PutObject`/`ListObjectsV2` | Bucket-Name in der Policy falsch | Inline-Policy der Rolle prüfen (beide Stellen) |
| `PermanentRedirect` / `301` | Region falsch | `S3_BACKUP_REGION` = Region des Buckets |
| `permission denied` auf `/backups/...` | `BACKUP_UID/GID` passt nicht zu den Dateien | `id deploy` mit `.env` vergleichen |

## Zurückholen aus S3 (Restore)

Der Server kann seine eigenen Sicherungen in S3 **nicht lesen** (so gewollt: ein Eindringling auf
dem Server kommt nicht an ältere Stände und kann nichts löschen). Geholt wird über die Konsole:

1. S3-Konsole → Bucket → `westbummeln/` → `daily/` (tägliche Sicherung) oder `pre-deploy/`
   (Stand vor einem Deploy) → Datei anhaken → **Download**.
   Ältere Fassung derselben Datei (z. B. wenn sie überschrieben wurde): Schalter **Show versions**
   an, die gewünschte Version anhaken → **Download**.
2. Vom PC auf den Server kopieren (PowerShell, im Download-Ordner):

   ```powershell
   scp .\westbummeln-20261126.sql.gz deploy@planspiel.7z2.de:/opt/westbummeln/backups/
   ```

3. Einspielen wie in [RUNBOOK.md](RUNBOOK.md), Abschnitt 4 „Backup einspielen“, mit dem Pfad
   `backups/westbummeln-20261126.sql.gz` (bzw. `pg_restore` für `.dump`).
4. Die heruntergeladene Datei vom PC löschen (enthält E-Mails und Passwort-Hashes).

Lokal durchgespielt (MinIO statt S3, mit genau der IAM-Policy aus `aws/`): Upload mit der
eingeschränkten Rolle, kein Doppel-Upload, Löschen/Lesen/fremde Ordner verweigert, überschriebene
Datei über die Versionen zurückgeholt, `.sql.gz` und `.dump` eingespielt, Daten wieder da.

## Ganzen Server aus einem Snapshot zurückholen

Schneller als Neuinstallation, wenn die Platte kaputt oder der Server verbastelt ist:

1. EC2 → **Instances** → Instanz anhaken → **Actions** → **Monitor and troubleshoot** →
   **Replace root volume**.
2. **Restore using:** **Snapshot** → den gewünschten Snapshot aus der Liste → **Create replacement
   task**. Die Instanz startet neu, IP (Elastic IP) und Rolle bleiben.
3. Danach wie nach jedem Neustart prüfen: `docker compose ps`, Spiel im Browser öffnen.

Alles seit dem Snapshot (bis zu 24 Stunden) ist weg. Fehlen danach Daten, die in einer späteren
Datenbank-Sicherung stecken, diese wie oben einspielen.
