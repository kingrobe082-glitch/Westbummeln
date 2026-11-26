#!/bin/sh
# Kopiert die Datenbank-Sicherungen nach S3 (zweite Kopie außerhalb des Servers).
# Läuft im Container "offsite" (rclone-Image, Alpine-sh), eingerichtet in docker-compose.prod.yml.
# Anleitung für AWS (Bucket, Rolle, Kosten): BACKUP-OFFSITE.md.
#
#   sh /offsite-backup.sh          Dauerbetrieb: sofort einmal kopieren, dann täglich um OFFSITE_TIME
#   sh /offsite-backup.sh once     einmal kopieren (Test): docker compose exec offsite sh /offsite-backup.sh once
#   sh /offsite-backup.sh health   Healthcheck: gesund, wenn aus oder letzte Kopie < 26 h alt
#
# Kopiert werden nur backups/daily/ und backups/pre-deploy/ (weekly/monthly/last sind dieselben
# Dumps noch einmal; S3 bewahrt selbst 90 Tage auf). Verweise (*-latest) und *.tmp bleiben liegen.
# rclone "copy" löscht nie etwas in S3. Die IAM-Rolle der Instanz darf auch nur auflisten und
# hochladen (deploy/aws/iam-policy-offsite-backup.json), nicht lesen oder löschen.
#
# Zugangsdaten: keine. rclone holt sich kurzlebige Schlüssel der EC2-Instanzrolle über IMDSv2
# (env_auth). Zum lokalen Testen gegen MinIO: S3_BACKUP_ENDPOINT, AWS_ACCESS_KEY_ID/SECRET setzen.
set -eu

BUCKET=${S3_BACKUP_BUCKET:-}
REGION=${S3_BACKUP_REGION:-eu-west-1}
PREFIX=${S3_BACKUP_PREFIX:-westbummeln}
AT=${OFFSITE_TIME:-04:00}            # Ortszeit (TZ), eine Stunde nach der täglichen Sicherung
SRC=${OFFSITE_SOURCE:-/backups}
STATE=/tmp/offsite-last-ok           # Unix-Zeit der letzten erfolgreichen Kopie
MAX_AGE=93600                        # 26 h

log() { printf '[offsite %s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"; }

# rclone-Ziel "s3:" nur über Umgebungsvariablen, keine Konfigurationsdatei.
export RCLONE_CONFIG=/dev/null
export RCLONE_CONFIG_S3_TYPE=s3
export RCLONE_CONFIG_S3_PROVIDER="${RCLONE_CONFIG_S3_PROVIDER:-AWS}"
export RCLONE_CONFIG_S3_ENV_AUTH=true
export RCLONE_CONFIG_S3_REGION="$REGION"
export RCLONE_CONFIG_S3_NO_CHECK_BUCKET=true   # kein CreateBucket/HeadBucket nötig
export RCLONE_CONFIG_S3_NO_HEAD=true           # kein HEAD nach dem Hochladen (Rolle darf nicht lesen)
if [ -n "${S3_BACKUP_ENDPOINT:-}" ]; then
  export RCLONE_CONFIG_S3_ENDPOINT="$S3_BACKUP_ENDPOINT"
fi

copy_once() {
  log "Kopiere $SRC/{daily,pre-deploy} nach s3://$BUCKET/$PREFIX/ ($REGION)"
  # --checksum: vergleicht MD5 mit dem ETag aus der Bucket-Liste. So reicht ListBucket, ohne
  # jedes Objekt einzeln abzufragen. Schon vorhandene, gleiche Dateien werden übersprungen.
  if rclone copy "$SRC" "s3:$BUCKET/$PREFIX/" \
      --filter '- *.tmp' \
      --filter '+ /daily/**' \
      --filter '+ /pre-deploy/**' \
      --filter '- **' \
      --skip-links --checksum \
      --retries 3 --low-level-retries 10 \
      --stats 0 -v 2>&1; then
    date +%s >"$STATE"
    log "OK"
    return 0
  fi
  log "FEHLER: Kopie nach S3 fehlgeschlagen (nächster Versuch in 1 h). Prüfen: BACKUP-OFFSITE.md, Abschnitt Fehlersuche."
  return 1
}

seconds_until() {   # Sekunden bis zur nächsten Uhrzeit $1 (HH:MM, Ortszeit)
  now=$(date +%s)
  t=$(date -d "$1" +%s)
  [ "$t" -gt "$now" ] || t=$((t + 86400))
  echo $((t - now))
}

case "${1:-loop}" in
  health)
    [ -n "$BUCKET" ] || exit 0           # aus: immer gesund
    [ -s "$STATE" ] || exit 1
    [ $(( $(date +%s) - $(cat "$STATE") )) -lt $MAX_AGE ]
    ;;
  once)
    [ -n "$BUCKET" ] || { log "S3_BACKUP_BUCKET ist leer: Kopie nach S3 ist aus."; exit 1; }
    copy_once
    ;;
  loop)
    if [ -z "$BUCKET" ]; then
      log "S3_BACKUP_BUCKET ist leer: Kopie nach S3 ist aus. Einschalten: BACKUP-OFFSITE.md."
      while :; do sleep 86400; done
    fi
    case "$AT" in [0-2][0-9]:[0-5][0-9]) ;; *) log "OFFSITE_TIME '$AT' ist nicht HH:MM."; exit 1 ;; esac
    while :; do
      if copy_once; then
        wait_s=$(seconds_until "$AT")
        log "Nächste Kopie um $AT (in $((wait_s / 60)) min)."
      else
        wait_s=3600
      fi
      sleep "$wait_s"
    done
    ;;
  *)
    echo "Aufruf: $0 [loop|once|health]" >&2
    exit 2
    ;;
esac
