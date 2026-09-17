#!/usr/bin/env bash
# Matchday chain (PRD 11 + 13): odds snapshots -> results -> predictions ->
# lock -> settle -> web export. Safe to run any time; every step is
# idempotent. Runs hourly from cron on the droplet (scripts/server/):
#   0 * * * * cd <repo> && ./scripts/matchday.sh >> data/status/matchday.log 2>&1
#
# Whatever happens, the EXIT trap records the run in data/status/runs.jsonl
# and pushes an ops snapshot to KV so /admin can show the failure.
set -eo pipefail
cd "$(dirname "$0")/.."
PY=.venv/bin/python
START=$(date +%s)
STEP=""
mkdir -p data/status

finish() {
  local rc=$?
  local dur=$(( $(date +%s) - START ))
  local ts; ts=$(date -u +%FT%TZ)
  if [[ $rc -eq 0 ]]; then
    printf '{"ts":"%s","ok":true,"failed_step":null,"duration_s":%d}\n' "$ts" "$dur" >> data/status/runs.jsonl
    $PY src/export_ops.py --run-ok --duration "$dur" || true
  else
    printf '{"ts":"%s","ok":false,"failed_step":"%s","duration_s":%d}\n' "$ts" "$STEP" "$dur" >> data/status/runs.jsonl
    $PY src/export_ops.py --run-failed "$STEP" --duration "$dur" || true
  fi
  ( cd web && npx wrangler kv key put ops --path src/data/ops.json --binding LIVE_KV --remote 2>&1 | grep -v -E 'Metrics|^\s*$' | grep -i -E 'error|fail' ) || true
  if [[ $rc -eq 0 ]]; then
    echo "matchday chain complete + KV updated (${dur}s) $(date -u +%H:%M) UTC"
  else
    echo "matchday chain FAILED at ${STEP} (${dur}s) $(date -u +%H:%M) UTC"
  fi
  exit $rc
}
trap finish EXIT

run() { STEP="$1"; shift; "$@"; }

run ingest_odds     $PY src/ingest_odds.py
run ingest_fixtures $PY src/ingest_fixtures.py --league-ids 39,140,135,78,253 --seasons 2026 --force-refresh
# All-competition fixtures (cups, Europe) for rest/congestion: ~110 calls,
# so twice a day rather than hourly.
if [[ "$(date -u +%H)" =~ ^(03|15)$ ]]; then
  run ingest_team_fixtures $PY src/ingest_team_fixtures.py --seasons 2026 --force-refresh
fi
# Transfermarkt squad values (public CSVs, re-downloaded weekly): daily.
if [[ "$(date -u +%H)" == "04" ]]; then
  run ingest_squad_values $PY src/ingest_squad_values.py
fi
# Player plus-minus ratings: refit monthly (1st, 06 UTC) from the lineup
# history now accumulating here; needs numpy in the server venv.
if [[ "$(date -u +%d%H)" == "0106" ]]; then
  for lg in pl lal bun sea; do run player_ratings_$lg $PY src/player_ratings.py --league $lg; done
fi
# Injuries (1 call per league) and confirmed lineups (1 call per newly
# played fixture; cached ones are skipped): daily, so missing-player and
# expected-XI features stay current on the server.
if [[ "$(date -u +%H)" == "05" ]]; then
  run ingest_injuries $PY src/ingest_injuries.py --league-ids 39,140,135,78,253 --seasons 2026 --force-refresh
  run ingest_lineups  $PY src/ingest_lineups.py --league-ids 39,140,135,78,253 --seasons 2026
fi
run predict         $PY src/predict.py --horizon-days 8 > /dev/null
run lock            $PY src/lifecycle.py lock --window-minutes 70
run settle          $PY src/lifecycle.py settle
# Betting ledger (Betting PRD 14): consensus per odds window, one graded
# row per locked prediction x market x selection (PASS included), CLV on
# settlement. Reads odds as of locked_at, so ordering after lock matters.
run betting         $PY src/betting/advisor.py
run export_web      $PY src/export_web.py
run kv_push bash -c 'cd web && npx wrangler kv key put live --path src/data/live.json --binding LIVE_KV --remote 2>&1 | grep -v -E "Metrics|^\s*$" | grep -i -E "error|fail|Writing"'
