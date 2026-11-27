# Tägliche Snapshots der Server-Platte

Die täglichen Datenbank-Sicherungen liegen auf derselben Platte wie die Datenbank
([RUNBOOK.md](RUNBOOK.md), Abschnitt 4). Ein täglicher EBS-Snapshot sichert die ganze Platte
getrennt davon. Einmal in der AWS-Konsole einrichten (Region **Europe (Frankfurt) eu-central-1**):

1. **EC2** → **Instances** → Instanz `i-038a2e99da4da8963` anklicken → Reiter **Storage** → die
   **Volume ID** (`vol-…`) anklicken.
2. Volume anhaken → Reiter **Tags** → **Manage tags** → **Add new tag**: Key `Backup`,
   Value `westbummeln` → **Save**.
3. EC2 → links **Elastic Block Store** → **Lifecycle Manager** → **Create lifecycle policy** →
   **Custom policy** und **EBS snapshot policy** → **Next**.
4. **Target resource types:** Volume. **Target resource tags:** `Backup` = `westbummeln` → **Add**.
   **Description:** `westbummeln täglich`. **IAM role:** Default role. **Policy status:** Enabled →
   **Next**.
5. **Frequency:** Daily, **Every:** 24 hours, **Starting at:** 02:30 UTC (nach der Sicherung um
   03:00 deutscher Zeit). **Retention type:** Count, **Keep:** 7. Haken bei **Copy tags from
   source** → **Review policy** → **Create policy**.
6. Am nächsten Tag prüfen: EC2 → **Elastic Block Store** → **Snapshots** → ein Snapshot
   „Created for policy …“ mit Status **Completed**. Nach einer Woche sind es dauerhaft 7.

**Kosten:** Snapshots speichern nur geänderte Blöcke, bei ~6 GB belegter Platte grob
0,50–0,80 $ pro Monat.

**Notfall (Platte kaputt oder Server verbastelt):**
EC2 → **Instances** → Instanz anhaken → **Actions** → **Monitor and troubleshoot** → **Replace root
volume** → **Restore using: Snapshot** → gewünschten Snapshot wählen → **Create replacement task**.
Die Instanz startet neu, Elastic IP bleibt; alles seit dem Snapshot (bis zu 24 h) ist weg.
