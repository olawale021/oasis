# Handoff: Oasis — five-league football prediction web app

## Overview
Oasis is a paid football prediction platform covering the Premier League, La Liga, Serie A,
Bundesliga and MLS (PRD: "Five-League Football Prediction Platform"). It publishes pre-match
probabilities, likely scores and the factors behind each forecast, and compares every model
probability against margin-free bookmaker probability ("edge").

This bundle covers three screens of the web MVP:

1. **Home — fixture rail** (primary home)
2. **Home — editorial cards** (alternative home treatment, same data)
3. **League page**

Not in this bundle (designed elsewhere in the exploration, ask if you need them): match detail,
performance/calibration page, pricing, account, admin.

## About the design files
`Oasis Web App.dc.html` is a **design reference written in HTML** — a prototype showing intended
look and behaviour. It is **not production code to copy**. Recreate these screens in the target
codebase using its established patterns and libraries. The PRD specifies a responsive web app with
**ShadCN UI** components on React; if no environment exists yet, that is the recommended target
(React + Tailwind + ShadCN).

Open the file by serving the folder (`python3 -m http.server`) and visiting the HTML file;
`support.js` must sit next to it. All styling is inline on purpose — that is an artifact of the
prototyping environment, not a pattern to reproduce. Extract it into Tailwind classes / tokens.

## Fidelity
**High fidelity.** Colours, typography, spacing, states and copy are final-intent. Recreate closely
using the codebase's component library; every value below is exact.

Data is realistic placeholder data (real club names, invented probabilities). Real numbers come
from the model pipeline.

## Screens / views

### 1. Home — fixture rail (`#3a`)
**Purpose:** an analyst scans today's fixtures, filters to the ones with a market edge, and expands
a row for the reasoning before opening the full match page.

**Layout:** 1180px reference width. Header bar (56px tall, 14px/22px padding, bottom 1px border),
then a 3-column grid: `212px | 1fr | 268px`, full-bleed columns divided by 1px borders (no gap).
Left rail and right rail have background `#111520`; centre column `#0f1218`, 18px/20px padding,
column gap between stacked blocks 14px.

**Header:** 22px rounded-6px logo mark with a `linear-gradient(140deg,#4d9cf6,#2fcf9a)` fill;
wordmark "Oasis" 16px/800. Nav items 13.5px/600 — active `#e9edf4`, inactive `#8b95a6`, 20px gap.
Right side: freshness pill (11.5px mono, `#6f7a8c`, 6px green `#2fcf9a` dot), primary button
("Get lifetime access") 12.5px/700, padding 7px 13px, radius 7px, background `#4d9cf6`, text
`#08101c`; 28px circular avatar `#232a36` with `#2e3646` border.

**Left rail:**
- Section labels: 10px/600 JetBrains Mono, letter-spacing .1em, `#6f7a8c`, uppercase.
- League list rows: 13px/600, padding 7px 9px, radius 7px, count right-aligned 11px mono `#6f7a8c`.
  Selected row: colour `#e9edf4`, background `#1c2431`. Unselected: `#8b95a6`, transparent.
  Hover: background `#1a2130`. Cursor pointer. Options: All leagues, Premier League, La Liga,
  Serie A, Bundesliga, MLS — each with its fixture count for the selected day.
- Filter chips (stacked, 12px/600, padding 7px 10px, radius 7px, 1px border `#232a36`):
  "Edge ≥ 3%" (active state: label gains " ✓", colour `#2fcf9a`, background `rgba(47,207,154,.08)`,
  border `rgba(47,207,154,.35)`), "Lineups confirmed", "High confidence".
- Data-freshness card: 1px `#232a36`, radius 9px, background `#12161d`, 11px mono lines
  (fixtures / injuries / odds timestamps).

**Centre column:**
- Day header: "Saturday 22 August" 19px/800, letter-spacing −.02em; subline
  `{selected league} · {n} match|matches` 11.5px mono `#8b95a6`; right-aligned day segmented control
  (Today / Tomorrow / Week) 11.5px/600, padding 5px 10px, radius 6px, active background `#1c2431`
  + border `#2e3646`.
- Table head: 10px/600 mono, letter-spacing .09em, `#6f7a8c`, bottom border `#232a36`.
  Columns: MATCH `250px` · MODEL · HOME / DRAW / AWAY `1fr` · SCORE `58px` right · EDGE `62px` right.
- Row: padding 12px 4px, bottom border `#1b212b`, cursor pointer, hover background `#151b26`.
  Rows with edge ≥ 3% get background `linear-gradient(90deg,rgba(47,207,154,.07),transparent 55%)`.
  - Fixture: `{home} v {away}` 14.5px/700, letter-spacing −.01em; the "v" is `#5b6474`/500.
  - Meta line: `{league} · {kickoff} · {lineup status}` 10.5px mono; `#2fcf9a` when lineups are
    confirmed, otherwise `#8b95a6`.
  - Probability bar: 9px tall, radius 5px, track `#1b212b`; segments home `#4d9cf6`,
    draw `#4a5464`, away `#e0863c`, widths = probabilities. Numeric readout `47/26/27`, 12px mono,
    86px wide.
  - Score 12.5px mono; edge 12px mono — `#2fcf9a`/700 when ≥ 3%, else `#6f7a8c`/500, always signed
    and one decimal.
- Expanded row (click toggles, one row open at a time): two-column grid `1.4fr | 1fr`, gap 16px,
  cards 1px `#232a36`, radius 9px, background `#12161d`, padding 12px.
  Left: "WHY THIS FORECAST" label + explanation 12.5px/1.7 `#c3cbd8`. Right: model vs market
  (no-vig) probabilities, confidence, likely score, and a "Open full match page →" link
  11.5px/700 `#4d9cf6`.
- Empty state (filters exclude everything): dashed `#2e3646` card, radius 9px, padding 22px,
  centred 13px/600 `#8b95a6`: "No fixtures match these filters today."
- Upsell band: radius 10px, 1px `#2e3646`,
  background `linear-gradient(120deg,rgba(77,156,246,.1),rgba(47,207,154,.06))`, padding 15px 17px;
  title 14.5px/700 "Free tier shows 3 matches a day", subline 11.5px mono `#8b95a6`
  "founding lifetime · 312 of 500 seats left", button "Unlock everything" as the primary button.

**Right rail:** "LAST 30 DAYS" card (log loss 0.981, vs market +0.006, calibration 0.021 — label
`#8b95a6`, value `#e9edf4`, 12px mono) with a 6-bar 44px sparkline (bars `#243044`→`#4d9cf6`,
radius 2px) and "See full record →" 11.5px/700 `#4d9cf6`; Telegram card (13px/600 title,
11px mono commands, outlined button "Connect account"); legal line 10px/1.6 mono `#5b6474`:
"Probabilistic forecasts, not guarantees and not betting advice. 18+ · responsible use."

### 2. Home — editorial cards (`#3b`)
**Purpose:** a lighter, explanation-first home for free/new users. 800px reference width.

Header identical in kind (20px mark, 15px wordmark, "Sign in" outlined button 12px/700,
border `#2e3646`). Body padding 20px, 16px stack gap.

- Title row: "Today's forecasts" 21px/800 + `{league} · {n} matches · published 06:00`
  11.5px mono `#8b95a6`.
- Featured match card (highest-edge fixture): 1px `#2e3646`, radius 12px, background `#12161d`,
  padding 18px. Title 18px/800; meta 11px mono; edge pill 11px mono, padding 4px 8px, radius 5px,
  background `rgba(47,207,154,.12)`, colour `#2fcf9a`. Three horizontal probability rows
  (label 96px `#8b95a6`, 11px track radius 6px, fills `#4d9cf6` / `#4a5464` / `#e0863c`,
  right-aligned percentage 44px). Chip row (11px mono, radius 6px, border `#232a36`): likely score,
  O2.5 54%, BTTS 51%, market split. Divider `#232a36` then explanation 13px/1.7 `#c3cbd8`.
- Two compact match rows: 1px `#232a36`, radius 11px, padding 15px, hover border `#2e3646`;
  200px probability bar, 78px numeric split, 48px score.
- Upsell card and two footer cards (30-day record / Telegram) as above.

### 3. League page (`#3c`)
**Purpose:** everything for one competition — fixtures with predictions, standings, and that
league's model record.

**Layout:** 1180px; header with the five leagues as tabs; filter bar; body grid `1.3fr | 1fr`
divided by a 1px `#232a36` border, each side padding 18px 20px.

- Tabs: 13.5px/600; active `#e9edf4` with 2px `#4d9cf6` bottom border, inactive `#8b95a6`
  transparent border, 3px bottom padding, cursor pointer.
- Filter bar: chips "Matchweek 2" (active), "Team: any", "Confidence: any"; right side
  `{league} · model v2.4.1` 11.5px mono `#6f7a8c`.
- Fixture cards: 1px `#232a36`, radius 10px, background `#12161d`, padding 13px, hover border
  `#2e3646`; 236px fixture block (14px/700 title + 10.5px mono `{kickoff} · {status}`), flexible
  probability bar, 80px numeric split `#8b95a6`, 42px score.
- Settlement card: "MATCHWEEK 1 SETTLEMENT", 12px/1.8 mono summary, "Open full ledger →".
- Standings table: 1px `#232a36`, radius 10px, header row 10px/600 mono `#6f7a8c`
  (# 26px · TEAM 1fr · P 28px · GD 38px · PTS 36px · ELO 52px, all but team right-aligned);
  rows 12px mono with team name 13px/700, alternate rows `rgba(255,255,255,.015)`,
  bottom border `#1b212b`.
- Model record card: three metrics (LOG LOSS, vs BASELINE in `#2fcf9a`, vs MARKET) at 21px mono
  with 10px/600 mono labels, plus a 6-bar 48px trend. Footnote 10px/1.6 mono `#5b6474`:
  "Lower log loss is better; negative vs baseline means the model beats league frequency."

## Interactions & behaviour
- **League selection** (left rail, screen 1): sets the active league; filters the fixture list;
  updates the day subline count and the editorial screen's featured match; collapses any expanded
  row. "All leagues" clears it.
- **Edge filter**: toggles a `edge ≥ 3%` predicate on the list; chip reflects state.
- **Row expand**: click a fixture row to open its explanation panel; clicking the open row closes
  it; only one row open at a time.
- **League tabs** (screen 3): switch fixtures, standings and the model-record card together.
- **Sorting**: the fixture list is sorted by edge, descending. Ties keep source order.
- **Copy rule**: match counts are singular/plural aware ("1 match" / "7 matches").
- Hover states are listed per component above; all clickable rows use `cursor: pointer`.
- No animations in this reference. If you add them, keep them ≤150ms ease-out; probability bars
  should not animate on data refresh (they would imply movement in the forecast).
- **Responsive** (not drawn, required by the PRD — mobile-first): below ~1000px collapse to one
  column, move the left rail into a horizontal scrolling league chip row, drop the right rail below
  the list, and let the fixture row wrap so the probability bar sits under the fixture name.

## State management
Prototype state (all client-side, would come from the server in production):

| State | Type | Trigger | Effect |
|---|---|---|---|
| `league` | `'ALL' \| 'EPL' \| 'LAL' \| 'SEA' \| 'BUN' \| 'MLS'` | league row / tab click | filters list, updates counts |
| `edgeOnly` | boolean | chip click | filters list to edge ≥ 3% |
| `expanded` | fixture id or null | row click | opens one explanation panel |
| `leagueTab` | league code | league-page tab click | swaps fixtures, standings, record |
| `day` | `'Today' \| 'Tomorrow' \| 'Week'` | segmented control | (stub in the reference) |

Derived per fixture: `edge = modelHome − marketHomeNoVig` (one decimal, signed); `hot = edge ≥ 3`;
probability split string; market split string; confidence band label.

Data the screens need per fixture: fixture id, league, kickoff (local + UTC), home/away names,
model home/draw/away probabilities, margin-free market probabilities, likely score, confidence
band, lineup status (`provisional` / `confirmed`), publication + last-update timestamps, short
explanation string, model version. Plus per league: standings rows (position, team, played, goal
difference, points, Elo) and model record (log loss, delta vs baseline, delta vs market, trend
series). Entitlement flag decides how many fixtures are visible (free = 3/day).

## Design tokens
**Colour**
| Token | Value | Use |
|---|---|---|
| `bg` | `#0f1218` | page / centre column |
| `bg-rail` | `#111520` | side rails |
| `surface` | `#12161d` | cards, header bar |
| `surface-raised` | `#1c2431` | active chip / segmented control |
| `border` | `#232a36` | card + section borders |
| `border-strong` | `#2e3646` | emphasis borders, outlined buttons |
| `border-row` | `#1b212b` | table row dividers, bar tracks |
| `hover-row` | `#151b26` | row hover |
| `text` | `#e9edf4` | primary text |
| `text-soft` | `#c3cbd8` | explanation prose |
| `text-muted` | `#8b95a6` | secondary text, labels |
| `text-dim` | `#6f7a8c` | table heads, meta |
| `text-faint` | `#5b6474` | legal, footnotes |
| `home` | `#4d9cf6` | home-win probability, primary action, links |
| `home-tint` | `rgba(77,156,246,.15)` | HIGH confidence badge |
| `home-ink` | `#08101c` | text on primary |
| `draw` | `#4a5464` | draw probability |
| `away` | `#e0863c` | away-win probability |
| `positive` | `#2fcf9a` | edge ≥ 3%, confirmed lineups, beats baseline |
| `positive-tint` | `rgba(47,207,154,.08–.12)` | active edge chip, edge pill |
| `warn` | `#eaa96e` | misses, incomplete availability |

**Type** — UI: Instrument Sans (weights 400/500/600/700/800; Manrope, Space Grotesk and Public Sans
were the tested alternates). Numerals and all labels: JetBrains Mono (400/500/700).
Scale in use: 21/19/18/16/15/14.5/13.5/13/12.5/12/11.5/10.5/10 px.
Headings 700–800 with letter-spacing −.01 to −.02em; mono labels 600 at 10px with .09–.1em tracking,
uppercase. All numeric columns are tabular mono, right-aligned.

**Spacing** 3 / 4 / 6 / 8 / 9 / 10 / 12 / 14 / 16 / 18 / 20 / 22 px.
**Radius** 5 (badges) / 6–7 (chips, buttons) / 9–12 (cards).
**Shadow** none in this reference — depth comes from borders and surface steps.
**Reference widths** 1180px (app screens), 800px (editorial home).

## Copy rules (from the PRD, treat as requirements)
- Never phrase a forecast as a guaranteed pick; always probabilities.
- Show "edge" as a probability difference, never as a recommended bet.
- Label the goals metric an **attack proxy**, never provider xG.
- Odds are a benchmark, never a model input — say so where odds appear.
- Every prediction surface carries the responsible-use line and 18+.
- Losses are never hidden; the record is immutable.

## Assets
None. No club crests, kits, player images or league marks are used — deliberately: the PRD requires
written confirmation of publication rights before any league/club imagery appears. Club names are
plain text. The logo mark is a CSS gradient placeholder pending brand work.

## Files
- `Oasis Web App.dc.html` — the three screens (ids `3a`, `3b`, `3c`), interactive.
- `support.js` — runtime required by the HTML reference. Not part of the product.
