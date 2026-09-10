#!/usr/bin/env bash
# Matchday chain (PRD 11 + 13): odds snapshots -> results -> predictions ->
# lock -> settle -> web export. Safe to run any time; every step is
# idempotent. Hourly cron recommended on matchdays:
#   0 * * * * ./scripts/matchday.sh >> data/status/matchday.log 2>&1
set -e
cd "$(dirname "$0")/.."
.venv/bin/python src/ingest_odds.py
.venv/bin/python src/ingest_fixtures.py --league-ids 39,140,135,78,253 --seasons 2026 --force-refresh
.venv/bin/python src/predict.py --horizon-days 8 > /dev/null
.venv/bin/python src/lifecycle.py lock --window-minutes 70
.venv/bin/python src/lifecycle.py settle
.venv/bin/python src/export_web.py
cd web && npx wrangler kv key put live --path src/data/live.json --binding LIVE_KV --remote && echo "matchday chain complete + KV updated $(date -u +%H:%M) UTC"
