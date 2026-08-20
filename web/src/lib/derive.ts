import { LEAGUE_NAMES } from "./data";
import type { DerivedMatch, MatchRecord } from "./types";

const EDGE_HOT_THRESHOLD = 3;

export function deriveMatch(m: MatchRecord): DerivedMatch {
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
    metaLabel: `${LEAGUE_NAMES[m.lg]} · ${m.ko} UTC · ${m.st}`,
  };
}

export function sortByKickoff(matches: DerivedMatch[]): DerivedMatch[] {
  return [...matches].sort((a, b) => a.kickoffUtc.localeCompare(b.kickoffUtc));
}

export function sortByEdgeDesc(matches: DerivedMatch[]): DerivedMatch[] {
  return [...matches].sort((a, b) => (b.edge ?? -Infinity) - (a.edge ?? -Infinity));
}
