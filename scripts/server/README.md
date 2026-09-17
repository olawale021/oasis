# Matchday server

The matchday chain (`scripts/matchday.sh`) runs hourly on a DigitalOcean
droplet (Ubuntu 24.04, 1 GB, London) and pushes `live.json` to Cloudflare
KV. The web app reads KV per request, so data never needs a redeploy. Site
code is deployed separately with `cd web && npm run cf:deploy`.

Measured peak RAM per step: predict 13 MB, export_web 167 MB, wrangler push
303 MB. Steps run sequentially, so 1 GB plus the 1 GB swap is comfortable.

## First-time setup

1. Commit and push the pipeline code. The server clones from GitHub, so
   anything uncommitted does not exist there.
2. Create the droplet: Ubuntu 24.04, Basic 1 GB, London, with your ssh key.
3. From the laptop:

       scp scripts/server/bootstrap.sh root@<ip>:/root/
       ssh root@<ip> bash bootstrap.sh

   It prints a deploy key and stops. Add it (read-only) at
   https://github.com/olawale021/oasis/settings/keys and run it again.
4. Copy the state once. `data/` is gitignored and holds the SQLite DB,
   model artifacts and raw archive (~640 MB):

       ./scripts/server/sync-data.sh oasis@<ip>

5. First run by hand, then watch the log:

       ssh oasis@<ip> 'cd oasis && ./scripts/matchday.sh'
       ssh oasis@<ip> 'tail -f oasis/data/status/matchday.log'

From then on the server's DB is the source of truth. Do not re-run
`sync-data.sh` without `--force`, and only after copying the server DB
back if you want to keep its locked/settled ledger.

## Cron on the droplet (user `oasis`)

| When (UTC) | What |
|---|---|
| every hour :00 | `scripts/matchday.sh` -- odds, fixtures, predictions, initial lock (70 min), settle, betting ledger, export, KV |
| every hour :30 | `src/ingest_odds.py --horizon-days 1` -- closing-line odds pass, so on-the-hour kickoffs get a `closing` snapshot (CLV) |
| :05, :15 ... :55 | `scripts/final_pass.sh` -- confirmed lineups inside 35 min -> final-stage lock -> re-export |
| 02:30 | `scripts/server/backup-db.sh` -- SQLite snapshot to data/backups (keeps 14) |
| 03:00, 15:00 | (inside matchday.sh) all-competition fixtures |
| 04:00 | (inside matchday.sh) Transfermarkt squad values |
| 05:00 | (inside matchday.sh) injuries + lineups |
| 1st of month 06:00 | (inside matchday.sh) player plus-minus ratings refit |

## Day to day

- Code change to the pipeline: `git push`, then `ssh oasis@<ip> 'cd oasis && git pull'`.
- Retrained models: `./scripts/server/push-models.sh oasis@<ip>` (models + registry + reports, then a chain run).
- Check health: the /admin page, or `ssh oasis@<ip> 'cat oasis/data/status/predict_status.json'`.
- Fresh DB for a refit: `./scripts/server/pull-db.sh oasis@<ip>` (installs the newest nightly backup locally).
- Secrets live in `oasis/.env` (API-Football) and `oasis/web/.env`
  (Cloudflare token + account id). Neither is in git.
