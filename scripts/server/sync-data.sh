#!/usr/bin/env bash
# Copy the gitignored state (SQLite DB, model artifacts, raw archive) and the
# two env files from this laptop to the server. Run ONCE after bootstrap.
# After that the server's database is the source of truth; re-running would
# overwrite newer locked/settled predictions with your stale local copy, so
# it refuses unless --force is given.
#
#   ./scripts/server/sync-data.sh oasis@<droplet-ip> [--force]
set -euo pipefail
HOST="${1:?usage: sync-data.sh oasis@<ip> [--force]}"
FORCE="${2:-}"
cd "$(dirname "$0")/../.."

if [[ "$FORCE" != "--force" ]] && ssh "$HOST" 'test -f oasis/data/oasis.sqlite'; then
  echo "Server already has data/oasis.sqlite. Re-run with --force to overwrite." >&2
  exit 1
fi

for f in .env web/.env; do
  [[ -f "$f" ]] || { echo "missing $f" >&2; exit 1; }
done

rsync -az --info=progress2 --exclude '__pycache__' --exclude '*.sqlite-journal' data/ "$HOST:oasis/data/"
rsync -az .env "$HOST:oasis/.env"
rsync -az web/.env "$HOST:oasis/web/.env"
echo "Synced. Now: ssh $HOST 'cd oasis && ./scripts/matchday.sh'"
