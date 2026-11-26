#!/usr/bin/env bash
# Rollt eine neue Version von Westbummeln aus. Läuft auf dem Server in /opt/westbummeln als
# Benutzer deploy, aufgerufen von der GitHub Action (vorher: docker login ghcr.io):
#
#   IMAGE_TAG=<git-sha> ./remote-deploy.sh
#
# Ablauf: Images holen (web und alle anderen) -> Datenbank sichern (backups/pre-deploy) -> Stack starten -> bis zu 90 s auf
# den Healthcheck von web warten. Wird web nicht gesund, startet wieder die vorherige Version und
# das Skript endet mit Exit-Code 1 (2, wenn auch der Rückweg scheitert). Bei Erfolg steht der Tag in
# .deployed-tag und als IMAGE_TAG in .env, damit ein späteres "docker compose up -d" von Hand
# dieselbe Version startet und nicht ":latest".
#
# Achtung Rollback: Hat die neue Version schon Migrationen ausgeführt, läuft die alte Version auf
# dem neueren Datenbankschema. Bei reinen Erweiterungen (neue Felder/Tabellen) ist das harmlos.
# Sonst: Datenbank aus backups/pre-deploy einspielen (RUNBOOK.md).
set -euo pipefail

cd "$(dirname "$(readlink -f "$0")")"

IMAGE_REPO=ghcr.io/kingrobe082-glitch/westbummeln
HEALTH_TIMEOUT=${HEALTH_TIMEOUT:-90}
KEEP_IMAGES=3
KEEP_PREDEPLOY_DUMPS=5

log() { printf '[deploy %s] %s\n' "$(date '+%H:%M:%S')" "$*"; }
die() { log "FEHLER: $*"; exit 1; }

NEW_TAG=${IMAGE_TAG:-}
[[ -n "$NEW_TAG" ]] || die "IMAGE_TAG fehlt. Aufruf: IMAGE_TAG=<git-sha> ./remote-deploy.sh"
[[ "$NEW_TAG" =~ ^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$ ]] || die "IMAGE_TAG '$NEW_TAG' ist kein gültiger Docker-Tag."

[[ -f .env ]] || die ".env fehlt. Einmalig ./env-init.sh ausführen und die Werte prüfen (RUNBOOK.md)."
[[ -r .env ]] || die ".env ist nicht lesbar für $(id -un). Prüfen: ls -l .env"

# Ohne COMPOSE_FILE in .env (oder in der Umgebung) die Produktionsdatei nehmen.
if [[ -z "${COMPOSE_FILE:-}" ]] && ! grep -q '^COMPOSE_FILE=' .env; then
  export COMPOSE_FILE=docker-compose.prod.yml
fi

# Nie zwei Deploys gleichzeitig.
if command -v flock >/dev/null; then   # util-linux, auf Ubuntu immer da
  exec 9>.deploy.lock
  flock -n 9 || die "Es läuft schon ein Deploy (.deploy.lock)."
fi

# Vorabprüfung, bevor irgendetwas umgestellt wird.
IMAGE_TAG=$NEW_TAG docker compose config -q || die "docker compose config schlägt fehl. Es wurde nichts geändert."

web_container() { docker compose ps -q web 2>/dev/null | head -n1; }

# --- vorherige Version merken
PREV_TAG=""
if [[ -s .deployed-tag ]]; then
  PREV_TAG=$(<.deployed-tag)
else
  cid=$(web_container)
  if [[ -n "$cid" ]]; then
    image=$(docker inspect --format '{{.Config.Image}}' "$cid")
    PREV_TAG=${image##*:}
  fi
fi
log "Neue Version: $NEW_TAG, bisher: ${PREV_TAG:-(keine)}"

# --- Images holen (scheitert web, ist nichts verändert)
log "Hole $IMAGE_REPO:$NEW_TAG"
IMAGE_TAG=$NEW_TAG docker compose pull --quiet web || die "Image $IMAGE_REPO:$NEW_TAG nicht ladbar. Es wurde nichts geändert."
# Die übrigen Images (caddy, db, backup) auf den neuesten Stand ihres Tags bringen. "up -d" erstellt
# danach nur die Container neu, deren Image sich wirklich geändert hat; sonst läuft z. B. die
# Datenbank einfach weiter. Scheitert das (Docker Hub gestört), läuft der Deploy mit den lokalen
# Images weiter.
mapfile -t others < <(IMAGE_TAG=$NEW_TAG docker compose config --services | grep -vx web)
if (( ${#others[@]} )); then
  log "Hole Images für: ${others[*]}"
  IMAGE_TAG=$NEW_TAG docker compose pull --quiet "${others[@]}" \
    || log "WARNUNG: Nicht alle Images ladbar, es laufen die vorhandenen weiter."
fi

# --- Sicherung vor dem Deploy (nur wenn die Datenbank schon läuft)
db_cid=$(docker compose ps -q db 2>/dev/null | head -n1 || true)
if [[ -n "$db_cid" ]] && [[ "$(docker inspect --format '{{.State.Health.Status}}' "$db_cid" 2>/dev/null)" == healthy ]]; then
  mkdir -p backups/pre-deploy
  dump="backups/pre-deploy/$(date '+%Y%m%d-%H%M%S')_vor_${NEW_TAG:0:12}.dump"
  log "Sichere Datenbank nach $dump"
  if docker compose exec -T db pg_dump -U westbummeln -d westbummeln -Fc >"$dump.tmp"; then
    mv "$dump.tmp" "$dump"
    chmod 600 "$dump"
  else
    rm -f "$dump.tmp"
    die "Sicherung vor dem Deploy fehlgeschlagen. Es wurde nichts umgestellt."
  fi
  # Nur die letzten Sicherungen vor Deploys behalten (die tägliche Sicherung läuft getrennt).
  ls -1t backups/pre-deploy/*.dump 2>/dev/null | tail -n +$((KEEP_PREDEPLOY_DUMPS + 1)) | xargs -r rm -f --
fi

# --- warten, bis web mit dem gewünschten Image gesund ist
wait_healthy() {
  local want="$IMAGE_REPO:$1" deadline=$((SECONDS + HEALTH_TIMEOUT)) cid status image restarts
  while (( SECONDS < deadline )); do
    cid=$(web_container)
    if [[ -n "$cid" ]]; then
      image=$(docker inspect --format '{{.Config.Image}}' "$cid")
      status=$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$cid")
      restarts=$(docker inspect --format '{{.RestartCount}}' "$cid")
      if [[ "$image" == "$want" && "$status" == healthy ]]; then
        return 0
      fi
      if [[ "$image" == "$want" ]] && (( restarts >= 2 )); then
        log "web startet immer wieder neu (${restarts}x) – breche Warten ab."
        return 1
      fi
    fi
    sleep 3
  done
  log "web ist nach ${HEALTH_TIMEOUT}s nicht gesund (Status: ${status:-kein Container})."
  return 1
}

log "Starte Stack mit $NEW_TAG"
if IMAGE_TAG=$NEW_TAG docker compose up -d --remove-orphans && wait_healthy "$NEW_TAG"; then
  log "web ist gesund."
else
  log "Letzte Log-Zeilen von web:"
  docker compose logs --no-color --tail=60 web || true
  if [[ -z "$PREV_TAG" || "$PREV_TAG" == "$NEW_TAG" ]]; then
    die "Neue Version startet nicht und es gibt keine vorherige Version zum Zurückrollen."
  fi
  log "ROLLBACK auf $PREV_TAG"
  if IMAGE_TAG=$PREV_TAG docker compose up -d --remove-orphans && wait_healthy "$PREV_TAG"; then
    log "Rollback erfolgreich, es läuft wieder $PREV_TAG. Deploy von $NEW_TAG ist FEHLGESCHLAGEN."
    exit 1
  fi
  log "FEHLER: Auch der Rollback auf $PREV_TAG ist nicht gesund. Sofort von Hand prüfen (RUNBOOK.md)."
  exit 2
fi

# --- Tag festhalten: .deployed-tag und IMAGE_TAG in .env (Inode und Rechte von .env bleiben)
set_env_tag() {
  local tmp
  tmp=$(mktemp .env.XXXXXX)
  chmod 600 "$tmp"
  grep -v '^IMAGE_TAG=' .env >"$tmp" || true
  printf 'IMAGE_TAG=%s\n' "$1" >>"$tmp"
  cat "$tmp" >.env
  rm -f "$tmp"
}
set_env_tag "$NEW_TAG"
printf '%s\n' "$NEW_TAG" >.deployed-tag
printf '%s %s\n' "$(date -Iseconds)" "$NEW_TAG" >>.deploy-history

# --- Welches Image (Digest) läuft je Dienst? Damit lässt sich ein einzelnes Image-Update gezielt
# zurückrollen (RUNBOOK.md "Updates"). Nur die letzten 300 Zeilen bleiben.
for svc in $(docker compose config --services); do
  cid=$(docker compose ps -q "$svc" 2>/dev/null | head -n1)
  [[ -n "$cid" ]] || continue
  img=$(docker inspect --format '{{.Image}}' "$cid")
  ref=$(docker image inspect --format '{{if .RepoDigests}}{{index .RepoDigests 0}}{{end}}' "$img" 2>/dev/null || true)
  printf '%s %s %s %s\n' "$(date -Iseconds)" "$NEW_TAG" "$svc" "${ref:-$img}"
done >>.image-history
tail -n 300 .image-history >.image-history.tmp && mv .image-history.tmp .image-history

# --- Caddyfile geändert? Eine einzeln eingebundene Datei sieht der Container nach dem Ersetzen
# nicht (Bind-Mount hält die alte Inode), deshalb vergleichen und Caddy bei Bedarf neu erstellen.
if [[ "$(docker compose exec -T caddy cat /etc/caddy/Caddyfile 2>/dev/null | sha256sum)" != "$(sha256sum <Caddyfile)" ]]; then
  log "Caddyfile geändert – Caddy wird neu gestartet."
  docker compose up -d --force-recreate --no-deps caddy
fi

# --- alte Images aufräumen: die letzten $KEEP_IMAGES erfolgreich ausgerollten Tags bleiben
# (laut .deploy-history, die laufende Version steht dort ganz unten). Fehlgeschlagene fliegen raus.
keep=$(tac .deploy-history | awk '{print $2}' | awk '!seen[$0]++' | head -n "$KEEP_IMAGES")
for tag in $(docker image ls "$IMAGE_REPO" --format '{{.Tag}}' | grep -v '<none>' || true); do
  if [[ "$tag" == "$NEW_TAG" || "$tag" == latest ]] || grep -qxF "$tag" <<<"$keep"; then
    continue
  fi
  if docker image rm "$IMAGE_REPO:$tag" >/dev/null 2>&1; then log "Altes Image entfernt: $tag"; fi
done
docker image prune -f --filter "until=24h" >/dev/null || true

log "Fertig: $NEW_TAG läuft."
