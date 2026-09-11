#!/usr/bin/env bash
# Copy the server's newest nightly backup to this laptop and install it as
# data/oasis.sqlite (the previous local copy is kept with a date suffix).
# Use before a refit so training sees the current season and the live ledger.
#   ./scripts/server/pull-db.sh oasis@<ip>
set -euo pipefail
HOST="${1:?usage: pull-db.sh oasis@<ip>}"
cd "$(dirname "$0")/../.."
LATEST=$(ssh "$HOST" 'ls -1t oasis/data/backups/oasis-*.sqlite.gz 2>/dev/null | head -1')
[[ -n "$LATEST" ]] || { echo "no backups on server yet (backup-db.sh runs nightly at 02:30 UTC)" >&2; exit 1; }
rsync -az "$HOST:$LATEST" data/backups/ 2>/dev/null || { mkdir -p data/backups; rsync -az "$HOST:$LATEST" data/backups/; }
FILE="data/backups/$(basename "$LATEST")"
[[ -f data/oasis.sqlite ]] && mv data/oasis.sqlite "data/oasis.sqlite.laptop_$(date -u +%Y%m%d)"
gzip -dc "$FILE" > data/oasis.sqlite
echo "installed $(basename "$LATEST") as data/oasis.sqlite"
