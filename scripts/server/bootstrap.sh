#!/usr/bin/env bash
# One-shot server setup for the Oasis matchday chain on a DigitalOcean
# droplet (Ubuntu 24.04, 1 GB). Run as root over ssh. Idempotent: safe to
# re-run. Stops after printing the deploy key the first time; re-run once
# the key is added on GitHub.
#
#   scp scripts/server/bootstrap.sh root@<ip>:/root/ && ssh root@<ip> bash bootstrap.sh
set -euo pipefail

REPO="git@github.com:olawale021/oasis.git"
APP_USER="oasis"
APP_DIR="/home/${APP_USER}/oasis"
WRANGLER_VERSION="4.124.0"   # keep in step with web/package.json

log() { printf '\n==> %s\n' "$*"; }

log "System packages + timezone"
timedatectl set-timezone UTC
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq git python3 python3-venv sqlite3 rsync curl ca-certificates

if ! command -v node >/dev/null || [[ "$(node -v)" != v22* ]]; then
  log "Node 22 LTS"
  curl -fsSL https://deb.nodesource.com/setup_22.x | bash - >/dev/null
  apt-get install -y -qq nodejs
fi
npm ls -g wrangler >/dev/null 2>&1 || npm install -g "wrangler@${WRANGLER_VERSION}" >/dev/null

if [[ ! -f /swapfile ]]; then
  log "1 GB swap (safety margin for the wrangler push)"
  fallocate -l 1G /swapfile && chmod 600 /swapfile && mkswap /swapfile >/dev/null && swapon /swapfile
  echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

if ! id -u "$APP_USER" >/dev/null 2>&1; then
  log "Create user ${APP_USER}"
  adduser --disabled-password --gecos "" "$APP_USER"
fi
install -d -m 700 -o "$APP_USER" -g "$APP_USER" "/home/${APP_USER}/.ssh"
# Let the laptop's ssh key (already on root) reach the app user for rsync.
if [[ -s /root/.ssh/authorized_keys ]]; then
  install -m 600 -o "$APP_USER" -g "$APP_USER" /root/.ssh/authorized_keys "/home/${APP_USER}/.ssh/authorized_keys"
else
  echo "WARNING: no /root/.ssh/authorized_keys -- run 'ssh-copy-id root@<ip>' from the laptop first, then re-run, or sync-data.sh cannot log in as ${APP_USER}." >&2
fi

run_as() { sudo -u "$APP_USER" -H bash -c "$*"; }

if [[ ! -f "/home/${APP_USER}/.ssh/id_ed25519" ]]; then
  run_as 'ssh-keygen -t ed25519 -N "" -f ~/.ssh/id_ed25519 -C oasis-droplet -q'
fi
run_as 'grep -q github.com ~/.ssh/known_hosts 2>/dev/null || ssh-keyscan -t ed25519 github.com >> ~/.ssh/known_hosts 2>/dev/null'

if ! run_as 'ssh -T -o BatchMode=yes git@github.com 2>&1 | grep -q "successfully authenticated"'; then
  cat <<MSG

Add this READ-ONLY deploy key at https://github.com/olawale021/oasis/settings/keys
then re-run this script:

$(cat "/home/${APP_USER}/.ssh/id_ed25519.pub")

MSG
  exit 1
fi

if [[ -d "${APP_DIR}/.git" ]]; then
  log "Update repo"
  run_as "cd '${APP_DIR}' && git pull --ff-only"
else
  log "Clone repo"
  run_as "git clone '${REPO}' '${APP_DIR}'"
fi

log "Python venv (runtime deps only; training deps are not needed here)"
run_as "cd '${APP_DIR}' && [[ -d .venv ]] || python3 -m venv .venv"
run_as "cd '${APP_DIR}' && .venv/bin/pip install -q -r requirements.txt"
run_as "mkdir -p '${APP_DIR}/data/status'"
run_as "chmod +x '${APP_DIR}/scripts/matchday.sh'"

log "Hourly cron for ${APP_USER}"
CRON_LINE="0 * * * * cd ${APP_DIR} && ./scripts/matchday.sh >> data/status/matchday.log 2>&1"
run_as "( echo 'PATH=/usr/local/bin:/usr/bin:/bin'; echo '${CRON_LINE}' ) | crontab -"
run_as 'crontab -l'

cat <<MSG

Server ready. Remaining steps, from your laptop:

  1. ./scripts/server/sync-data.sh ${APP_USER}@$(curl -fsS -4 ifconfig.me || echo '<ip>')
     (copies data/, .env and web/.env once -- the DB lives here from now on)
  2. ssh ${APP_USER}@<ip> 'cd oasis && ./scripts/matchday.sh'   # first run by hand
  3. ssh ${APP_USER}@<ip> 'tail -f oasis/data/status/matchday.log'

Code updates later: ssh ${APP_USER}@<ip> 'cd oasis && git pull'
MSG
