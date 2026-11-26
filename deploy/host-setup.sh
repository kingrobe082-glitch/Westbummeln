#!/usr/bin/env bash
# Host-Setup fuer den Westbummeln-Server (Ubuntu 26.04 LTS, AWS EC2 t3.micro).
#
# Aufruf (als ubuntu, Skript und oeffentlicher Deploy-Schluessel vorher per scp hochgeladen):
#   sudo bash host-setup.sh /tmp/westbummeln_deploy.pub
# Ohne Schluessel-Argument wird alles eingerichtet, authorized_keys von deploy bleibt unveraendert.
#
# Idempotent: mehrfaches Ausfuehren aendert nur, was vom Sollzustand abweicht.
# Docker wird nur neu gestartet, wenn sich /etc/docker/daemon.json geaendert hat.
# Details, Pruefschritte und Notfallzugang: deploy/RUNBOOK-SERVER.md
set -euo pipefail

if [[ $(id -u) -ne 0 ]]; then echo "bitte mit sudo ausfuehren" >&2; exit 1; fi

PUBKEY_FILE="${1:-}"
APP_DIR=/opt/westbummeln
DEPLOY_USER=deploy
HOSTNAME_WANTED=westbummeln
TZ_WANTED=Europe/Berlin
SWAPFILE=/swapfile
SWAP_SIZE=2G

export DEBIAN_FRONTEND=noninteractive
export NEEDRESTART_MODE=a
APT_OPTS=(-y -q -o Dpkg::Options::=--force-confdef -o Dpkg::Options::=--force-confold)

log() { printf '\n==> %s\n' "$*"; }

# Schreibt Datei $1 mit Inhalt von stdin, Modus $2. Rueckgabe 0 = geaendert, 1 = unveraendert.
write_file() {
  local path=$1 mode=${2:-0644} tmp
  tmp=$(mktemp)
  cat > "$tmp"
  if [[ -f $path ]] && cmp -s "$tmp" "$path"; then rm -f "$tmp"; return 1; fi
  install -D -m "$mode" "$tmp" "$path"
  rm -f "$tmp"
  echo "   geschrieben: $path"
  return 0
}

if [[ -n $PUBKEY_FILE ]]; then
  [[ -r $PUBKEY_FILE ]] || { echo "Schluesseldatei $PUBKEY_FILE nicht lesbar" >&2; exit 1; }
  PUBKEY=$(grep -E '^ssh-ed25519 [A-Za-z0-9+/=]+( .*)?$' "$PUBKEY_FILE" | head -n1 || true)
  [[ -n $PUBKEY ]] || { echo "$PUBKEY_FILE enthaelt keinen ssh-ed25519-Schluessel" >&2; exit 1; }
fi

# ---------------------------------------------------------------------------
log "Hostname und Zeitzone"
hostnamectl set-hostname "$HOSTNAME_WANTED"
grep -qE "^127\.0\.1\.1\s+$HOSTNAME_WANTED\b" /etc/hosts || echo "127.0.1.1 $HOSTNAME_WANTED" >> /etc/hosts
# cloud-init setzt den Hostnamen sonst bei jedem Boot auf ip-172-... zurueck
write_file /etc/cloud/cloud.cfg.d/99-westbummeln.cfg <<'EOF' || true
preserve_hostname: true
EOF
timedatectl set-timezone "$TZ_WANTED"

# ---------------------------------------------------------------------------
log "Pakete aktualisieren (full-upgrade)"
apt-get update -q
apt-get full-upgrade "${APT_OPTS[@]}"
apt-get install "${APT_OPTS[@]}" ca-certificates curl gnupg unattended-upgrades ufw fail2ban python3-systemd

# ---------------------------------------------------------------------------
log "unattended-upgrades (Sicherheitsupdates, Neustart 04:00 erlaubt)"
write_file /etc/apt/apt.conf.d/20auto-upgrades <<'EOF' || true
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
APT::Periodic::AutocleanInterval "7";
EOF
write_file /etc/apt/apt.conf.d/52westbummeln-unattended <<'EOF' || true
Unattended-Upgrade::Automatic-Reboot "true";
Unattended-Upgrade::Automatic-Reboot-WithUsers "true";
Unattended-Upgrade::Automatic-Reboot-Time "04:00";
Unattended-Upgrade::Remove-Unused-Kernel-Packages "true";
Unattended-Upgrade::Remove-Unused-Dependencies "true";
EOF
systemctl enable --now unattended-upgrades.service >/dev/null

# ---------------------------------------------------------------------------
log "Swap ${SWAP_SIZE} unter ${SWAPFILE}"
if [[ ! -f $SWAPFILE ]]; then
  fallocate -l "$SWAP_SIZE" "$SWAPFILE" || dd if=/dev/zero of="$SWAPFILE" bs=1M count=2048 status=none
  chmod 600 "$SWAPFILE"
  mkswap "$SWAPFILE" >/dev/null
fi
chmod 600 "$SWAPFILE"
swapon --show=NAME --noheadings | grep -qx "$SWAPFILE" || swapon "$SWAPFILE"
grep -qE "^$SWAPFILE\s" /etc/fstab || echo "$SWAPFILE none swap sw 0 0" >> /etc/fstab

write_file /etc/sysctl.d/99-westbummeln.conf <<'EOF' || true
# wenig RAM (t3.micro): Swap nur als Notreserve
vm.swappiness = 10
# Netzwerk-Haertung
net.ipv4.conf.all.accept_redirects = 0
net.ipv4.conf.default.accept_redirects = 0
net.ipv6.conf.all.accept_redirects = 0
net.ipv4.conf.all.send_redirects = 0
net.ipv4.tcp_syncookies = 1
EOF
sysctl --system >/dev/null

# ---------------------------------------------------------------------------
log "Docker Engine + Compose-Plugin"
. /etc/os-release
CODENAME=${UBUNTU_CODENAME:-$VERSION_CODENAME}
ARCH=$(dpkg --print-architecture)
if ! command -v docker >/dev/null 2>&1; then
  if curl -fsS -o /dev/null "https://download.docker.com/linux/ubuntu/dists/${CODENAME}/stable/binary-${ARCH}/Packages"; then
    install -m 0755 -d /etc/apt/keyrings
    [[ -s /etc/apt/keyrings/docker.asc ]] || curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
    chmod a+r /etc/apt/keyrings/docker.asc
    write_file /etc/apt/sources.list.d/docker.sources <<EOF || true
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: ${CODENAME}
Components: stable
Architectures: ${ARCH}
Signed-By: /etc/apt/keyrings/docker.asc
EOF
    apt-get update -q
    apt-get install "${APT_OPTS[@]}" docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
    echo "   Quelle: offizielles Docker-Repo (${CODENAME})"
  else
    # Fallback, falls Docker fuer diese Ubuntu-Version noch kein Repo hat
    apt-get install "${APT_OPTS[@]}" docker.io docker-compose-v2
    echo "   Quelle: Ubuntu-Pakete docker.io + docker-compose-v2 (kein Docker-Repo fuer ${CODENAME})"
  fi
fi

# live-restore: Container laufen weiter, wenn der Docker-Daemon neu startet (z. B. Docker-Update).
# Wichtig, weil der Spielzustand nur im Speicher des Django-Containers liegt.
if write_file /etc/docker/daemon.json <<'EOF'
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "20m",
    "max-file": "5"
  },
  "live-restore": true
}
EOF
then
  systemctl restart docker
fi
systemctl enable --now docker.service containerd.service >/dev/null

# ---------------------------------------------------------------------------
log "Benutzer ${DEPLOY_USER} (Gruppe docker, kein Passwort, kein sudo)"
if ! id "$DEPLOY_USER" >/dev/null 2>&1; then
  useradd --create-home --shell /bin/bash --groups docker "$DEPLOY_USER"
fi
usermod -aG docker "$DEPLOY_USER"
usermod -p '*' "$DEPLOY_USER"          # kein gueltiges Passwort, Login nur per Schluessel
if id -nG "$DEPLOY_USER" | tr ' ' '\n' | grep -qxE 'sudo|admin'; then
  echo "   WARNUNG: ${DEPLOY_USER} ist in einer sudo-Gruppe - bitte pruefen" >&2
fi
DEPLOY_HOME=$(getent passwd "$DEPLOY_USER" | cut -d: -f6)
install -d -m 700 -o "$DEPLOY_USER" -g "$DEPLOY_USER" "$DEPLOY_HOME/.ssh"
AUTH_KEYS="$DEPLOY_HOME/.ssh/authorized_keys"
[[ -f $AUTH_KEYS ]] || install -m 600 -o "$DEPLOY_USER" -g "$DEPLOY_USER" /dev/null "$AUTH_KEYS"
if [[ -n ${PUBKEY:-} ]]; then
  KEY_BLOB=$(awk '{print $2}' <<<"$PUBKEY")
  if grep -qF "$KEY_BLOB" "$AUTH_KEYS"; then
    # vorhandene Zeile mit diesem Schluessel durch die Soll-Zeile (mit restrict) ersetzen
    grep -vF "$KEY_BLOB" "$AUTH_KEYS" > "$AUTH_KEYS.new" || true
  else
    cp "$AUTH_KEYS" "$AUTH_KEYS.new"
  fi
  echo "restrict $PUBKEY" >> "$AUTH_KEYS.new"
  if cmp -s "$AUTH_KEYS.new" "$AUTH_KEYS"; then rm -f "$AUTH_KEYS.new"; else
    mv "$AUTH_KEYS.new" "$AUTH_KEYS"; echo "   Deploy-Schluessel eingetragen (restrict)"
  fi
fi
chown "$DEPLOY_USER:$DEPLOY_USER" "$AUTH_KEYS"
chmod 600 "$AUTH_KEYS"

# ---------------------------------------------------------------------------
log "Anwendungsordner ${APP_DIR}"
install -d -m 750 -o "$DEPLOY_USER" -g "$DEPLOY_USER" "$APP_DIR"
install -d -m 750 -o "$DEPLOY_USER" -g "$DEPLOY_USER" "$APP_DIR/backups"

# ---------------------------------------------------------------------------
log "Firewall (ufw)"
ufw default deny incoming >/dev/null
ufw default allow outgoing >/dev/null
ufw allow 22/tcp  comment 'ssh'    >/dev/null
ufw allow 80/tcp  comment 'http'   >/dev/null
ufw allow 443/tcp comment 'https'  >/dev/null
ufw allow 443/udp comment 'http3'  >/dev/null
# Aussperr-Schutz: nur aktivieren, wenn die SSH-Regel wirklich drinsteht
if ! ufw show added | grep -qE 'allow 22/tcp'; then
  echo "SSH-Regel fehlt - ufw wird NICHT aktiviert" >&2; exit 1
fi
ufw --force enable >/dev/null
ufw status verbose | sed 's/^/   /'

# ---------------------------------------------------------------------------
log "sshd haerten"
SSHD_DROPIN=/etc/ssh/sshd_config.d/10-westbummeln.conf
# Drop-ins werden alphabetisch gelesen, der erste Wert gewinnt -> 10- vor 60-cloudimg-settings
SSHD_BACKUP=$(mktemp)
had_dropin=0
if [[ -f $SSHD_DROPIN ]]; then cp -p "$SSHD_DROPIN" "$SSHD_BACKUP"; had_dropin=1; fi
if write_file "$SSHD_DROPIN" <<'EOF'
# verwaltet von deploy/host-setup.sh (Westbummeln)
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin no
PermitEmptyPasswords no
PubkeyAuthentication yes
X11Forwarding no
MaxAuthTries 4
LoginGraceTime 30
EOF
then
  if sshd -t; then
    systemctl try-reload-or-restart ssh.service
    echo "   sshd neu geladen (bestehende Verbindungen bleiben offen)"
  else
    echo "sshd -t schlaegt fehl - Drop-in wird zurueckgenommen" >&2
    if [[ $had_dropin -eq 1 ]]; then cp -p "$SSHD_BACKUP" "$SSHD_DROPIN"; else rm -f "$SSHD_DROPIN"; fi
    rm -f "$SSHD_BACKUP"
    exit 1
  fi
fi
rm -f "$SSHD_BACKUP"
sshd -t

# ---------------------------------------------------------------------------
log "fail2ban fuer sshd"
if write_file /etc/fail2ban/jail.d/westbummeln.local <<'EOF'
[sshd]
enabled  = true
backend  = systemd
maxretry = 5
findtime = 10m
bantime  = 1h
EOF
then
  systemctl restart fail2ban
fi
systemctl enable --now fail2ban.service >/dev/null

# ---------------------------------------------------------------------------
log "Zusammenfassung"
echo "   Hostname:   $(hostname)   Zeitzone: $(timedatectl show -p Timezone --value)"
echo "   Docker:     $(docker --version)"
echo "   Compose:    $(docker compose version)"
echo "   Swap:       $(swapon --show=NAME,SIZE --noheadings | tr -s ' ')   swappiness=$(sysctl -n vm.swappiness)"
echo "   ${DEPLOY_USER}:     $(id "$DEPLOY_USER")"
echo "   ${APP_DIR}: $(stat -c '%U:%G %a' "$APP_DIR")"
echo "   fail2ban:   $(fail2ban-client status sshd 2>/dev/null | grep -m1 'Currently banned' | tr -s ' \t' ' ' || echo '?')"
if [[ -f /var/run/reboot-required ]]; then
  echo "   HINWEIS: Neustart erforderlich (Kernel/Bibliotheken aktualisiert): sudo reboot"
fi
echo "Host-Setup fertig."
