#!/usr/bin/env bash
# Legt /opt/westbummeln/.env einmalig an: Vorlage .env.example mit zufälligem SECRET_KEY und
# POSTGRES_PASSWORD, BACKUP_UID/GID des aufrufenden Benutzers. Eine vorhandene .env wird NIE
# überschrieben (das Datenbank-Passwort steht dann schon im Volume der Datenbank).
#
#   ./env-init.sh [DOMAIN] [ACME_EMAIL]
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"

if [[ -e .env ]]; then
  echo ".env existiert schon – nichts geändert."
  exit 0
fi
[[ -f .env.example ]] || { echo "FEHLER: .env.example fehlt." >&2; exit 1; }

random() { # $1 Zeichen aus [A-Za-z0-9]
  local out=""
  while (( ${#out} < $1 )); do
    out+=$(head -c 256 /dev/urandom | LC_ALL=C tr -dc 'A-Za-z0-9')
  done
  printf '%s' "${out:0:$1}"
}

secret_key=$(random 64)
db_password=$(random 40)
domain=${1:-}
email=${2:-}

umask 077
tmp=$(mktemp .env.XXXXXX)
sed -e "s|^SECRET_KEY=.*|SECRET_KEY=${secret_key}|" \
    -e "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=${db_password}|" \
    -e "s|^BACKUP_UID=.*|BACKUP_UID=$(id -u)|" \
    -e "s|^BACKUP_GID=.*|BACKUP_GID=$(id -g)|" \
    .env.example >"$tmp"
if [[ -n "$domain" ]]; then sed -i "s|^DOMAIN=.*|DOMAIN=${domain}|" "$tmp"; fi
if [[ -n "$email" ]]; then sed -i "s|^ACME_EMAIL=.*|ACME_EMAIL=${email}|" "$tmp"; fi
mv "$tmp" .env
chmod 600 .env
mkdir -p backups
chmod 750 backups

echo ".env angelegt (chmod 600). Jetzt prüfen und ergänzen:"
echo "  DOMAIN, ACME_EMAIL, DEVELOPER_USERNAME, DEVELOPER_PASSWORD"
echo "  nano .env"
