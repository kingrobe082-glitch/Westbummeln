#!/usr/bin/env bash
# Liest Konten im alten Format (Backup-JSON oder accounts.sqlite3 des früheren Servers) in die
# Datenbank auf diesem Server ein. Für die Neuinstallation nicht nötig, nur für den Fall der Fälle.
#
#   ./import-accounts.sh /pfad/zu/accounts-backup.json      (oder eine alte accounts.sqlite3)
#
# Die Datei z. B. per scp nach /opt/westbummeln/ kopieren. Ablauf: Datei in den
# laufenden web-Container kopieren, Probelauf (speichert nichts), Rückfrage, echter Import,
# Datei im Container wieder löschen. Der Import ist idempotent: ein zweiter Lauf ändert nichts.
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"

src=${1:-}
[[ -n "$src" && -f "$src" ]] || { echo "Aufruf: ./import-accounts.sh <accounts-backup.json|accounts.sqlite3>" >&2; exit 1; }

if [[ -z "${COMPOSE_FILE:-}" ]] && ! grep -qs '^COMPOSE_FILE=' .env; then
  export COMPOSE_FILE=docker-compose.prod.yml
fi

[[ -n "$(docker compose ps -q web </dev/null)" ]] || { echo "FEHLER: web läuft nicht (docker compose ps)." >&2; exit 1; }

target=/tmp/legacy-import
cleanup() { docker compose exec -T -u 0 web rm -f "$target" </dev/null >/dev/null 2>&1 || true; }
trap cleanup EXIT

docker compose cp "$src" "web:$target" </dev/null
# docker cp legt die Datei als root an; der App-Benutzer muss sie lesen können.
# </dev/null: exec -T würde sonst die Antwort auf die Rückfrage unten von stdin wegnehmen.
docker compose exec -T -u 0 web chown app:app "$target" </dev/null
docker compose exec -T -u 0 web chmod 600 "$target" </dev/null

echo "=== Probelauf (speichert nichts) ==="
docker compose exec -T web python manage.py import_legacy_accounts "$target" --probelauf </dev/null

echo
read -r -p "Sieht das gut aus? Jetzt wirklich importieren? [j/N] " answer
if [[ ! "$answer" =~ ^[jJyY]$ ]]; then
  echo "Abgebrochen, nichts importiert."
  exit 0
fi

echo "=== Import ==="
docker compose exec -T web python manage.py import_legacy_accounts "$target" </dev/null
echo
echo "Fertig. Die Quelldatei $src enthält E-Mails und Passwort-Hashes: danach löschen (rm $src)."
