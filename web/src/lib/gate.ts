import "server-only";
import type { LiveData } from "./data";
import type { MatchRecord } from "./types";
import type { Viewer } from "./viewer";

/** Access gating for upcoming predictions. Runs in server components only,
 * before the payload reaches any client component, so gated fields never
 * ship to the browser.
 *
 * Rules (decided 2026-09-12):
 *  - premium: everything.
 *  - free:    today's taster fixtures in full, everything else gated.
 *  - anon:    every upcoming prediction gated.
 * Finished matches live in `recent_results` and the performance ledger and
 * are never gated. */

export const TASTER_PER_DAY = 2;

const EMPTY_MATRIX = { grid: [], peakRow: 0, peakCol: 0, peakPct: 0, over15: 0, over25: 0, over35: 0, btts: 0 };

function utcToday(): string {
  return new Date().toISOString().slice(0, 10);
}

/** Today's taster ids. Prefers the set pinned by the matchday chain; if the
 * payload predates today (chain not yet run), falls back to the same rule
 * computed live: highest top-outcome probability, earliest kickoff, id. */
export function tasterIds(live: LiveData): Set<number> {
  const today = utcToday();
  const pinned = live.taster?.[today];
  if (pinned) return new Set(pinned);
  const todays = live.matches
    .filter((m) => m.kickoffUtc.slice(0, 10) === today)
    .sort((x, y) =>
      Math.max(y.h, y.d, y.a) - Math.max(x.h, x.d, x.a) ||
      x.kickoffUtc.localeCompare(y.kickoffUtc) ||
      x.id - y.id,
    );
  return new Set(todays.slice(0, TASTER_PER_DAY).map((m) => m.id));
}

export function redactMatch(m: MatchRecord): MatchRecord {
  return {
    ...m,
    h: 0, d: 0, a: 0,
    mh: null, md: null, ma: null,
    marketSnapshot: null, marketBookmakers: null,
    score: "", conf: "LOW", why: "",
    muHome: 0, muAway: 0,
    matrix: EMPTY_MATRIX,
    condScore: "", condPct: 0,
    pick: "draw",
    missingHome: 0, missingAway: 0,
    factors: [],
    gated: true,
  };
}

export function canSee(viewer: Viewer, matchId: number, taster: Set<number>): boolean {
  if (viewer.tier === "premium") return true;
  if (viewer.tier === "free") return taster.has(matchId);
  return false;
}

/** Copy of the live payload with prediction fields stripped from every
 * upcoming match this viewer may not see. Cheap: the match list is small. */
export function redactLive(live: LiveData, viewer: Viewer): LiveData {
  if (viewer.tier === "premium") return live;
  const taster = tasterIds(live);
  return {
    ...live,
    matches: live.matches.map((m) => (canSee(viewer, m.id, taster) ? m : redactMatch(m))),
  };
}
