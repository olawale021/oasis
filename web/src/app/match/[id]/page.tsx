import { Fragment } from "react";
import { notFound } from "next/navigation";
import Link from "next/link";
import { Badge } from "@/components/ui/badge";
import { AlertToggle } from "@/components/match/alert-toggle";
import { getMatchById, marketTotals, utcClock } from "@/lib/data";
import { getLive } from "@/lib/live-server";
import { getViewer } from "@/lib/viewer";
import { redactLive } from "@/lib/gate";
import { UnlockCta } from "@/components/unlock-cta";
import { deriveMatch } from "@/lib/derive";
import { MatchName, TeamLogo } from "@/components/team-logo";
import { IconLock } from "@/components/icons";

export const dynamic = "force-dynamic";

const MATRIX_DISPLAY_GOALS = 5;

function utcStamp(iso: string): string {
  const d = new Date(iso);
  return `${d.toLocaleDateString("en-GB", { weekday: "short", timeZone: "UTC" })} ${utcClock(iso)}`;
}

export default async function MatchDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const viewer = await getViewer();
  const live = redactLive(await getLive(), viewer);
  const record = getMatchById(live, Number(id));
  if (!record) notFound();

  const m = deriveMatch(record);
  const totals = marketTotals(live, m.id);
  if (m.gated) {
    return (
      <div className="flex w-full flex-col gap-6 p-4 sm:p-6">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-[var(--oasis-border)] pb-4">
          <Link href="/" className="font-mono text-[12px] font-semibold text-[var(--oasis-text-dim)]">
            ← Board
          </Link>
          <span className="text-title font-bold">
            <MatchName home={m.home} away={m.away} homeId={m.homeId} awayId={m.awayId} size={26} />
          </span>
          <span className="font-mono text-[11.5px] font-medium text-[var(--oasis-text-muted)]">
            {m.leagueName} · {m.ko} UTC{m.round ? ` · ${m.round}` : ""}
          </span>
          <span className="ml-auto flex gap-2">
            <Badge
              variant="outline"
              className="font-mono text-[10px] font-semibold tracking-[0.08em] text-[var(--oasis-text-muted)]"
            >
              MODEL {(live.model_versions[m.lg] ?? "").toUpperCase()}
            </Badge>
          </span>
        </div>

        <div className="flex max-w-[640px] flex-col gap-5">
          <div
            className="flex h-11 items-center justify-center rounded-[9px] font-mono text-[12px] font-semibold tracking-[0.1em] text-[var(--oasis-text-dim)]"
            style={{ background: "repeating-linear-gradient(135deg, var(--oasis-border-row) 0 8px, var(--oasis-surface-raised) 8px 16px)", border: "1px solid var(--oasis-border)" }}
          >
            <IconLock size={13} />
            <span className="ml-[7px]">PREDICTION LOCKED</span>
          </div>
          <div className="max-w-[560px] text-[13.5px] leading-[1.7] text-[var(--oasis-text-soft)]">
            {viewer.tier === "anon" ? (
              <>A free account shows the two highest-confidence predictions each day. Lifetime access shows every upcoming match with win probabilities, likely score, score matrix, the factors behind the forecast and the comparison against bookmaker odds.</>
            ) : (
              <>This match is outside today&rsquo;s free taster. Lifetime access shows every upcoming match with win probabilities, likely score, score matrix, the factors behind the forecast and the comparison against bookmaker odds.</>
            )}{" "}
            Once the match finishes, the locked prediction and its verdict become public under Results.
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <UnlockCta tier={viewer.tier} />
            <Link href="/performance" className="text-[12.5px] font-bold text-[var(--oasis-home)]">
              See the public track record →
            </Link>
          </div>
        </div>

        <div className="font-mono text-[10px] font-medium leading-[1.6] text-[var(--oasis-text-faint)]">
          Prediction locks at kickoff {utcStamp(m.kickoffUtc)} UTC · no edits after kickoff. Probabilistic forecast, not betting advice. 18+ · responsible use.
        </div>
      </div>
    );
  }
  const matrix = m.matrix;
  const grid = matrix.grid.slice(0, MATRIX_DISPLAY_GOALS).map((row) => row.slice(0, MATRIX_DISPLAY_GOALS));
  const peakVisible = matrix.peakRow < MATRIX_DISPLAY_GOALS && matrix.peakCol < MATRIX_DISPLAY_GOALS;
  const hasMarket = m.mh !== null && m.md !== null && m.ma !== null;

  const timeline = [
    {
      label: "Initial",
      time: utcStamp(live.predictions_generated_at),
      detail: `${m.probsLabel} · pre-lineup model run`,
      tone: "final" as const,
    },
    {
      label: "Final",
      time: "pending",
      detail: "regenerated after confirmed lineups, ~30–60 min before kickoff",
      tone: "pending" as const,
    },
    {
      label: "Locks at kickoff",
      time: utcStamp(m.kickoffUtc),
      detail: "no edits after kickoff",
      tone: "pending" as const,
    },
  ];

  return (
    <div className="flex w-full flex-col gap-6 p-4 sm:p-6">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-[var(--oasis-border)] pb-4">
        <Link href="/" className="font-mono text-[12px] font-semibold text-[var(--oasis-text-dim)]">
          ← Board
        </Link>
        <span className="text-title font-bold">
          <MatchName home={m.home} away={m.away} homeId={m.homeId} awayId={m.awayId} size={26} />
        </span>
        <span className="font-mono text-[11.5px] font-medium text-[var(--oasis-text-muted)]">
          {m.leagueName} · {m.ko} UTC{m.round ? ` · ${m.round}` : ""}
        </span>
        <span className="ml-auto flex gap-2">
          <Badge
            className="font-mono text-[10px] font-bold tracking-[0.08em]"
            style={{
              background: m.statusConfirmed ? "var(--oasis-positive-tint)" : "var(--oasis-surface-raised)",
              color: m.statusConfirmed ? "var(--oasis-positive)" : "var(--oasis-text-muted)",
              border: `1px solid ${m.statusConfirmed ? "rgba(47,207,154,.3)" : "var(--oasis-border-strong)"}`,
            }}
          >
            {m.st.toUpperCase()}
          </Badge>
          <Badge
            variant="outline"
            className="font-mono text-[10px] font-semibold tracking-[0.08em] text-[var(--oasis-text-muted)]"
          >
            MODEL {(live.model_versions[m.lg] ?? "").toUpperCase()}
          </Badge>
        </span>
      </div>

      <div className="flex flex-col gap-4">
        <div className="flex flex-col gap-[9px]">
          <div className="flex h-11 overflow-hidden rounded-[9px]">
            <div
              className="flex items-center justify-center overflow-hidden whitespace-nowrap font-mono text-[12.5px] font-bold text-[var(--oasis-home-ink)] sm:text-[15px]"
              style={{ width: `${m.h}%`, background: "var(--oasis-home)" }}
            >
              {m.h.toFixed(1)}%
            </div>
            <div
              className="flex items-center justify-center overflow-hidden whitespace-nowrap font-mono text-[12.5px] font-bold sm:text-[15px]"
              style={{ width: `${m.d}%`, background: "var(--oasis-draw)" }}
            >
              {m.d.toFixed(1)}%
            </div>
            <div
              className="flex items-center justify-center overflow-hidden whitespace-nowrap font-mono text-[12.5px] font-bold text-[#1a1206] sm:text-[15px]"
              style={{ width: `${m.a}%`, background: "var(--oasis-away)" }}
            >
              {m.a.toFixed(1)}%
            </div>
          </div>
          <div className="flex justify-between gap-2 font-mono text-[9px] font-semibold tracking-[0.07em] text-[var(--oasis-text-muted)] sm:text-[10.5px]">
            <span>{m.home.toUpperCase()} WIN</span>
            <span>DRAW</span>
            <span>{m.away.toUpperCase()} WIN</span>
          </div>
        </div>
        <div className="grid grid-cols-2 gap-[8px] sm:grid-cols-3 lg:grid-cols-6">
          <Stat
            label="Likely score"
            value={m.condScore}
            sub={`${Math.round(m.condPct)}% chance${m.pick !== "draw" ? ` · if ${m.pick === "home" ? m.home : m.away} win` : ""}`}
          />
          <Stat label="Most common score" value={m.score} sub={`${Math.round(m.matrix.peakPct)}% chance · any result`} />
          <Stat label="Expected goals" value={`${m.muHome.toFixed(1)} – ${m.muAway.toFixed(1)}`} sub={`${m.home} – ${m.away}`} />
          {/* Totals lead with the bookmaker consensus: on held-out seasons the
              goals model is at or near the base rate for these markets (see
              Performance), so its number is shown as the footnote, not the claim. */}
          <Stat
            label="Over 2.5 goals"
            value={totals.over25 ? `${Math.round(totals.over25.mp)}%` : `${Math.round(matrix.over25)}%`}
            sub={totals.over25 ? `bookmakers (${totals.over25.books ?? "—"}) · model ${Math.round(matrix.over25)}%, not validated` : "model · not validated · no odds yet"}
          />
          <Stat
            label="Both teams score"
            value={totals.btts ? `${Math.round(totals.btts.mp)}%` : `${Math.round(matrix.btts)}%`}
            sub={totals.btts ? `bookmakers (${totals.btts.books ?? "—"}) · model ${Math.round(matrix.btts)}%, not validated` : "model · not validated · no odds yet"}
          />
          <Stat
            label="Edge vs market"
            value={m.edgeLabel}
            sub={m.edge === null ? "no odds yet" : `${m.home} win · model minus market`}
            valueColor={m.edge !== null ? (m.edge >= 0 ? "var(--oasis-positive)" : "var(--oasis-away)") : undefined}
          />
        </div>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[1fr_1fr_320px]">
        <div className="flex flex-col gap-[10px] rounded-[10px] border border-[var(--oasis-border)] bg-[var(--oasis-surface)] p-4">
          <div className="font-mono text-[10px] font-semibold tracking-[0.1em] text-[var(--oasis-text-dim)]">
            SCORE PROBABILITY MATRIX · GOALS MODEL, INDICATIVE
          </div>
          <div className="grid grid-cols-[16px_repeat(5,1fr)] gap-[4px]">
            <div />
            {[0, 1, 2, 3, 4].map((c) => (
              <div key={c} className="text-center font-mono text-[9.5px] font-medium text-[var(--oasis-text-dim)]">
                {c}
              </div>
            ))}
            {grid.map((row, i) => (
              <Fragment key={i}>
                <div className="flex items-center font-mono text-[9.5px] font-medium text-[var(--oasis-text-dim)]">
                  {i}
                </div>
                {row.map((cell, j) => {
                  const isPeak = peakVisible && i === matrix.peakRow && j === matrix.peakCol;
                  return (
                    <div
                      key={j}
                      className="flex aspect-square items-center justify-center rounded-[4px] font-mono text-[10px] font-bold"
                      style={
                        isPeak
                          ? { background: "var(--oasis-home)", color: "var(--oasis-home-ink)" }
                          : { background: `rgba(77,156,246,${Math.min(0.5, cell / 20)})` }
                      }
                    >
                      {isPeak ? cell.toFixed(1) : ""}
                    </div>
                  );
                })}
              </Fragment>
            ))}
          </div>
          <div className="font-mono text-[10px] font-medium text-[var(--oasis-text-faint)]">
            rows = {m.home} goals · columns = {m.away} goals · Dixon–Coles Poisson
          </div>
          <div className="font-mono text-[10px] font-medium leading-[1.5] text-[var(--oasis-text-faint)]">
            The shape is the model&rsquo;s view of the fixture. Its totals are at or near the base rate on held-out
            seasons, so the Over 2.5 and BTTS figures above are the bookmaker consensus, not this grid.
          </div>
        </div>

        <div className="flex flex-col gap-[11px] rounded-[10px] border border-[var(--oasis-border)] bg-[var(--oasis-surface)] p-4">
          <div className="font-mono text-[10px] font-semibold tracking-[0.1em] text-[var(--oasis-text-dim)]">
            WHAT MOVED THIS FORECAST
          </div>
          {m.factors.map((f) => (
            <div key={f.label} className="flex items-center gap-[10px]">
              <span
                className="w-[104px] cursor-help text-[11.5px] font-semibold sm:w-[132px] sm:text-[12.5px]"
                title={live.factor_glossary?.[f.label] ?? f.label}
              >
                {f.label}
              </span>
              <span className="flex flex-1">
                {f.weight >= 0 ? (
                  <>
                    <span className="w-1/2" />
                    <span className="flex w-1/2">
                      <span
                        className="h-[10px] rounded-r-[4px]"
                        style={{ width: `${Math.min(100, Math.abs(f.weight) * 130)}%`, background: "var(--oasis-home)" }}
                      />
                    </span>
                  </>
                ) : (
                  <>
                    <span className="flex w-1/2 justify-end">
                      <span
                        className="h-[10px] rounded-l-[4px]"
                        style={{ width: `${Math.min(100, Math.abs(f.weight) * 130)}%`, background: "var(--oasis-away)" }}
                      />
                    </span>
                    <span className="w-1/2" />
                  </>
                )}
              </span>
              <span
                className="w-[42px] text-right font-mono text-[11.5px] font-medium"
                style={{ color: f.weight >= 0 ? "#8fc2ff" : "var(--oasis-warn)" }}
              >
                {f.weight >= 0 ? "+" : ""}
                {f.weight.toFixed(2)}
              </span>
            </div>
          ))}
          {m.factors.length === 0 && (
            <div className="text-[12px] font-medium text-[var(--oasis-text-muted)]">
              No single factor moves this forecast much — the sides profile as evenly matched.
            </div>
          )}
          <div className="border-t border-[var(--oasis-border)] pt-[10px] font-mono text-[10.5px] font-medium leading-[1.5] text-[var(--oasis-text-dim)]">
            contribution to the home-vs-away logit, standardized features · temperature-calibrated · odds are benchmark
            only, never a model input
          </div>

          <div className="mt-1 font-mono text-[10px] font-semibold tracking-[0.1em] text-[var(--oasis-text-dim)]">
            MODEL vs MARKET
          </div>
          {hasMarket ? (
            <div className="flex flex-col gap-2 font-mono text-[12px] font-medium">
              <div className="flex text-[10px] tracking-[0.06em] text-[var(--oasis-text-dim)]">
                <span className="flex-1">OUTCOME</span>
                <span className="w-14 text-right">MODEL</span>
                <span className="w-[74px] text-right">MKT (no vig)</span>
                <span className="w-[54px] text-right">DIFF</span>
              </div>
              <MarketRow label={m.home} model={m.h} market={m.mh as number} />
              <MarketRow label="Draw" model={m.d} market={m.md as number} />
              <MarketRow label={m.away} model={m.a} market={m.ma as number} />
              <div className="pt-1 text-[10px] text-[var(--oasis-text-dim)]">
                median of {m.marketBookmakers} bookmakers · margin removed · {m.marketSnapshot} snapshot · benchmark
                only, never a model input
              </div>
            </div>
          ) : (
            <div className="rounded-[7px] border border-dashed border-[var(--oasis-border-strong)] p-3 font-mono text-[11px] font-medium leading-[1.6] text-[var(--oasis-text-muted)]">
              No odds archive yet — market comparison starts when odds collection begins at launch.
            </div>
          )}
        </div>

        <div className="flex flex-col gap-3">
          <div className="flex flex-col gap-3 rounded-[10px] border border-[var(--oasis-border)] bg-[var(--oasis-surface)] p-4">
            <div className="font-mono text-[10px] font-semibold tracking-[0.1em] text-[var(--oasis-text-dim)]">
              PREDICTION TIMELINE
            </div>
            {timeline.map((stage) => (
              <div key={stage.label} className="flex gap-[11px]" style={{ opacity: stage.tone === "pending" ? 0.65 : 1 }}>
                <span
                  className="mt-[5px] h-[9px] w-[9px] flex-none rounded-full"
                  style={
                    stage.tone === "pending"
                      ? { border: "1px dashed var(--oasis-text-dim)" }
                      : { background: "var(--oasis-positive)" }
                  }
                />
                <span>
                  <span className="text-[12.5px] font-bold">{stage.label}</span>{" "}
                  {stage.time && (
                    <span className="font-mono text-[10.5px] font-medium text-[var(--oasis-text-dim)]">{stage.time}</span>
                  )}
                  <div className="font-mono text-[11.5px] font-medium text-[var(--oasis-text-muted)]">{stage.detail}</div>
                </span>
              </div>
            ))}
          </div>

          <div className="flex flex-col gap-2 rounded-[10px] border border-[var(--oasis-border)] bg-[var(--oasis-surface)] p-4">
            <div className="font-mono text-[10px] font-semibold tracking-[0.1em] text-[var(--oasis-text-dim)]">
              AVAILABILITY
            </div>
            <div className="flex justify-between text-[12.5px] font-semibold">
              <span className="flex items-center gap-[7px]"><TeamLogo id={m.homeId} size={18} />{m.home}</span>
              <span
                className="font-mono text-[11.5px] font-medium"
                style={{ color: m.missingHome === 0 ? "var(--oasis-positive)" : "var(--oasis-warn)" }}
              >
                {m.missingHome === 0 ? "no reported absences" : `${m.missingHome} out`}
              </span>
            </div>
            <div className="flex justify-between text-[12.5px] font-semibold">
              <span className="flex items-center gap-[7px]"><TeamLogo id={m.awayId} size={18} />{m.away}</span>
              <span
                className="font-mono text-[11.5px] font-medium"
                style={{ color: m.missingAway === 0 ? "var(--oasis-positive)" : "var(--oasis-warn)" }}
              >
                {m.missingAway === 0 ? "no reported absences" : `${m.missingAway} out`}
              </span>
            </div>
            <div className="font-mono text-[10.5px] font-medium text-[var(--oasis-text-faint)]">
              injuries updated {utcClock(live.freshness.injuries)} UTC · lineups not yet confirmed
            </div>
          </div>

          <AlertToggle />

          <div className="font-mono text-[10px] font-medium leading-[1.6] text-[var(--oasis-text-faint)]">
            Probabilistic forecast, not betting advice. 18+ · responsible use.
          </div>
        </div>
      </div>
    </div>
  );
}

function Stat({ label, value, sub, valueColor }: { label: string; value: string; sub?: string; valueColor?: string }) {
  return (
    <div className="min-w-0 rounded-[8px] border border-[var(--oasis-border)] bg-[var(--oasis-bg)] px-3 py-[9px]">
      <div className="truncate font-mono text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--oasis-text-dim)]">{label}</div>
      <div className="mt-[2px] whitespace-nowrap font-mono text-[19px] font-semibold leading-tight sm:text-[22px]" style={{ color: valueColor }}>
        {value}
      </div>
      {sub && <div className="mt-[3px] truncate text-[11px] font-medium text-[var(--oasis-text-muted)]">{sub}</div>}
    </div>
  );
}


function MarketRow({ label, model, market }: { label: string; model: number; market: number }) {
  const diff = Math.round((model - market) * 10) / 10;
  return (
    <div className="flex">
      <span className="flex-1">{label}</span>
      <span className="w-14 text-right">{model.toFixed(1)}</span>
      <span className="w-[74px] text-right text-[var(--oasis-text-muted)]">{market.toFixed(1)}</span>
      <span
        className="w-[54px] text-right"
        style={{ color: diff > 0.05 ? "var(--oasis-positive)" : diff < -0.05 ? "var(--oasis-warn)" : "var(--oasis-text-dim)" }}
      >
        {diff > 0 ? "+" : ""}
        {diff.toFixed(1)}
      </span>
    </div>
  );
}
