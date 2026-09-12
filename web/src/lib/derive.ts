import { LEAGUE_NAMES } from "./data";
import type { DerivedMatch, MatchRecord } from "./types";

const EDGE_HOT_THRESHOLD = 3;

export function deriveMatch(m: MatchRecord): DerivedMatch {
  const statusConfirmedEarly = m.st.includes("confirmed");
  if (m.gated) {
    return {
      ...m,
      leagueName: LEAGUE_NAMES[m.lg],
      probsLabel: "—",
      marketLabel: null,
      edge: null,
      edgeLabel: "—",
      hot: false,
      statusConfirmed: statusConfirmedEarly,
      metaLabel: `${LEAGUE_NAMES[m.lg]} · ${m.ko} UTC${statusConfirmedEarly ? " · lineups confirmed" : ""}`,
    };
  }
  // Market probabilities come from archived odds snapshots; a fixture with
  // no snapshot yet stays null — there is never a fake edge.
  const hasMarket = m.mh !== null && m.md !== null && m.ma !== null;
  const edge = hasMarket ? Math.round((m.h - (m.mh as number)) * 10) / 10 : null;
  const hot = edge !== null && edge >= EDGE_HOT_THRESHOLD;
  const statusConfirmed = m.st.includes("confirmed");

  return {
    ...m,
    leagueName: LEAGUE_NAMES[m.lg],
    probsLabel: `${Math.round(m.h)}/${Math.round(m.d)}/${Math.round(m.a)}`,
    marketLabel: hasMarket
      ? `${Math.round(m.mh as number)}/${Math.round(m.md as number)}/${Math.round(m.ma as number)}`
      : null,
    edge,
    edgeLabel: edge !== null ? `${edge > 0 ? "+" : ""}${edge.toFixed(1)}%` : "—",
    hot,
    statusConfirmed,
    // Stage text only when it carries news: "lineups confirmed" (green).
    // The default "initial · lineups pending" is noise on every row.
    metaLabel: `${LEAGUE_NAMES[m.lg]} · ${m.ko} UTC${statusConfirmed ? " · lineups confirmed" : ""}`,
  };
}

export function sortByKickoff(matches: DerivedMatch[]): DerivedMatch[] {
  return [...matches].sort((a, b) => a.kickoffUtc.localeCompare(b.kickoffUtc));
}

export function sortByEdgeDesc(matches: DerivedMatch[]): DerivedMatch[] {
  return [...matches].sort((a, b) => (b.edge ?? -Infinity) - (a.edge ?? -Infinity));
}
