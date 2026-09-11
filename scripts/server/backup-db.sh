#!/usr/bin/env bash
# Nightly on the droplet: consistent SQLite snapshot (online backup API,
# safe while the chain writes) -> data/backups/oasis-YYYYMMDD-HHMM.sqlite.gz,
# keep the newest 14. Pull one to the laptop with scripts/server/pull-db.sh.
#   30 2 * * * cd /home/oasis/oasis && ./scripts/server/backup-db.sh >> data/status/backup.log 2>&1
set -euo pipefail
cd "$(dirname "$0")/../.."
mkdir -p data/backups
STAMP=$(date -u +%Y%m%d-%H%M)
OUT="data/backups/oasis-${STAMP}.sqlite"
sqlite3 data/oasis.sqlite ".backup '${OUT}'"
gzip -f "$OUT"
ls -1t data/backups/oasis-*.sqlite.gz | tail -n +15 | xargs -r rm -f
echo "backup ${OUT}.gz $(du -h "${OUT}.gz" | cut -f1) $(date -u +%FT%TZ)"
