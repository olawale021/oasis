#!/usr/bin/env bash
# Push retrained model artifacts (+ registry) and harness reports from this
# laptop to the server, then pull code and run the chain there so the next
# predictions come from the new release.
#
#   ./scripts/server/push-models.sh oasis@<droplet-ip>
set -euo pipefail
HOST="${1:?usage: push-models.sh oasis@<ip>}"
cd "$(dirname "$0")/../.."
rsync -az --delete --exclude 'player_ratings_*.json' data/models/ "$HOST:oasis/data/models/"
rsync -az --ignore-existing data/models/player_ratings_*.json "$HOST:oasis/data/models/"  # seed only; the server refits monthly
rsync -az data/reports/ "$HOST:oasis/data/reports/"
ssh "$HOST" 'cd oasis && git pull -q --ff-only && ./scripts/matchday.sh 2>&1 | grep -E "complete|FAILED|Traceback"'
ssh "$HOST" 'cd oasis && python3 -c "import json;d=json.load(open(\"outputs/predictions.json\"));print({k:v[\"outcome\"][\"version\"] for k,v in d[\"model_registry\"].items()})"'
