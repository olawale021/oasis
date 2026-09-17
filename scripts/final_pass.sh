#!/usr/bin/env bash
# Final-stage pass (PRD 13.2): every 10 minutes at :05,:15,...,:55 so it
# never overlaps the hourly chain. Cheap when nothing kicks off soon (one
# SQL query); near kickoffs it fetches lineups and locks a final-stage
# prediction, then re-exports the site so the board shows confirmed-XI
# probabilities within minutes.
#   5-55/10 * * * * cd <repo> && ./scripts/final_pass.sh >> data/status/final_pass.log 2>&1
set -eo pipefail
cd "$(dirname "$0")/.."
PY=.venv/bin/python
N=$($PY src/final_stage.py --window-minutes 35 | tail -1)
if [[ "${N:-0}" -gt 0 ]]; then
  $PY src/export_web.py > /dev/null
  ( cd web && npx wrangler kv key put live --path src/data/live.json --binding LIVE_KV --remote 2>&1 | grep -i -E "error|fail" ) || true
  $PY src/telegram_dispatch.py || true
  echo "final pass: $N fixture(s) locked at final stage, site updated $(date -u +%H:%M) UTC"
fi
