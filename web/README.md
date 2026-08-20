# Oasis web

Next.js (App Router) frontend implementing the Oasis prediction-platform
design. TypeScript, Tailwind CSS, shadcn/ui. All data is mock data
(`src/lib/`) — there is no API or database wiring yet; see the repo-root
`PRD.md` for where this fits (Phase 3: Web MVP).

Visual direction: **production reference** handoff in
`design_handoff_oasis_web/` (screens `3a`/`3b`/`3c`) — a flat "dark analyst"
palette (`#0f1218` surfaces, home-win blue `#4d9cf6`, away-win amber
`#e0863c`, green `#2fcf9a` reserved for edge/positive signals), not the
earlier glass/crimson-gold exploration. Design tokens live in
`src/app/globals.css` as `--oasis-*` custom properties; see
`design_handoff_oasis_web/README.md` for the full spec (colour, type,
spacing, states — treated as exact). That bundle is a design reference only,
excluded from lint/build.

## Develop

```bash
npm install
npm run dev       # http://localhost:8090
npm run build     # production build
npm run lint
```

## Pages

- `/` — home fixture rail (`3a`, primary home): league filter, edge≥3%
  toggle, expandable rows, day segmented control (Today only wired — a stub
  in the design reference too)
- `/home-editorial` — home editorial cards (`3b`, alternative home
  treatment): featured highest-edge match + two compact rows, aimed at
  free/new users. Routing between `3a`/`3b` (e.g. by entitlement) is a
  product decision, not yet made — both are just built as routes for now
- `/match/[id]` — match detail: probabilities, score matrix, factor weights,
  model-vs-market, prediction timeline (not in the design handoff bundle;
  re-skinned to the same tokens for visual consistency)
- `/league/[code]` — per-league fixtures, standings, model record (`3c`)
  (`EPL` / `LAL` / `SEA` / `BUN` / `MLS`)
- `/performance` — calibration, per-league and per-confidence-band
  breakdowns, prediction ledger (not in the design handoff bundle; re-skinned
  to the same tokens for visual consistency)

## Deploy (Cloudflare Workers)

Deployed via [`@opennextjs/cloudflare`](https://opennext.js.org/cloudflare),
configured in `wrangler.jsonc` and `open-next.config.ts`. This is a separate
Worker from the repo-root `wrangler.toml`, which only configures the R2 raw
API-Football archive used by the Python pipeline.

```bash
npm run cf:build     # build the Next.js app into a Cloudflare Worker
npm run cf:preview   # build + run it locally under workerd
npm run cf:deploy    # build + deploy to Cloudflare
```
