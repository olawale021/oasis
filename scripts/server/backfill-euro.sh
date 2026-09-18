#!/usr/bin/env bash
# One-time history backfill for the Champions League model on the server:
# the three UEFA competitions from 2010, the 25 domestic feeder leagues
# from 2014, Champions League injuries, and squad values for the new
# fixtures, plus shot stats and lineups for scored UCL fixtures. ~3,000 API calls
# (the daily quota is 7,500). Run AFTER `git pull` and BEFORE the first
# push-models.sh that carries outcome_model_ucl*.json -- predict.py replays
# the pooled European stream from history, so without this the Champions
# League ratings start cold.
#
#   ./scripts/server/backfill-euro.sh oasis@<droplet-ip>
set -euo pipefail
HOST="${1:?usage: backfill-euro.sh oasis@<ip>}"
ssh "$HOST" 'cd oasis && set -e
  PY=.venv/bin/python
  $PY src/ingest_fixtures.py --league-ids 2,3,848 --seasons 2010-2026 | tail -1
  $PY src/ingest_injuries.py --league-ids 2 --seasons 2017-2026 | tail -1
  $PY src/ingest_fixtures.py --league-ids 61,94,88,144,203,179,218,207,345,197,210,333,119,103,113,106,286,318,383,332,389,419,116,283,235 --seasons 2014-2026 | tail -1
  $PY src/ingest_squad_values.py 2>/dev/null | tail -1
  # Shot stats + confirmed lineups for scored Champions League fixtures (~1,300 calls each).
  $PY src/ingest_fixture_statistics.py --league-ids 2 --seasons 2017-2026 | tail -1
  $PY src/ingest_lineups.py --league-ids 2 --seasons 2017-2026 | tail -1
  sqlite3 data/oasis.sqlite "select league_id, count(*) from fixtures where league_id in (2,3,848) group by 1"'
