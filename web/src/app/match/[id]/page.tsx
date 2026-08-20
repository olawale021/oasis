import { Fragment } from "react";
import { notFound } from "next/navigation";
import Link from "next/link";
import { Badge } from "@/components/ui/badge";
import { AlertToggle } from "@/components/match/alert-toggle";
import { FRESHNESS, MATCHES, MODEL_VERSION, PREDICTIONS_GENERATED_AT, getMatchById, utcClock } from "@/lib/data";
import { deriveMatch } from "@/lib/derive";

export function generateStaticParams() {
  return MATCHES.map((m) => ({ id: String(m.id) }));
}

const MATRIX_DISPLAY_GOALS = 5;

function utcStamp(iso: string): string {
  const d = new Date(iso);
  return `${d.toLocaleDateString("en-GB", { weekday: "short", timeZone: "UTC" })} ${utcClock(iso)}`;
}

export default async function MatchDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const record = getMatchById(Number(id));
  if (!record) notFound();

  const m = deriveMatch(record);
  const matrix = m.matrix;
  const grid = matrix.grid.slice(0, MATRIX_DISPLAY_GOALS).map((row) => row.slice(0, MATRIX_DISPLAY_GOALS));
  const peakVisible = matrix.peakRow < MATRIX_DISPLAY_GOALS && matrix.peakCol < MATRIX_DISPLAY_GOALS;
  const hasMarket = m.mh !== null && m.md !== null && m.ma !== null;

  const timeline = [
    {
      label: "Initial",
      time: utcStamp(PREDICTIONS_GENERATED_AT),
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
    <div className="flex w-full flex-col gap-[14px] p-5">
      <div className="flex flex-wrap items-center gap-4 rounded-[10px] border border-[var(--oasis-border)] bg-[var(--oasis-surface)] p-4">
        <Link href="/" className="font-mono text-[12px] font-semibold text-[var(--oasis-text-dim)]">
          ← Board
        </Link>
        <span className="text-[21px] font-bold leading-none tracking-[-0.02em]">
          {m.home} <span className="font-medium text-[var(--oasis-text-faint)]">v</span> {m.away}
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
            MODEL {MODEL_VERSION.toUpperCase()}
          </Badge>
        </span>
      </div>

      <div className="flex flex-col gap-5 rounded-[10px] border border-[var(--oasis-border)] bg-[var(--oasis-surface)] p-5 md:flex-row md:items-center">
        <div className="flex flex-1 flex-col gap-[9px]">
          <div className="flex h-11 overflow-hidden rounded-[9px]">
            <div
              className="flex items-center justify-center font-mono text-[15px] font-bold text-[var(--oasis-home-ink)]"
              style={{ width: `${m.h}%`, background: "var(--oasis-home)" }}
            >
              {m.h.toFixed(1)}%
            </div>
            <div
              className="flex items-center justify-center font-mono text-[15px] font-bold"
              style={{ width: `${m.d}%`, background: "var(--oasis-draw)" }}
            >
              {m.d.toFixed(1)}%
            </div>
            <div
              className="flex items-center justify-center font-mono text-[15px] font-bold text-[#1a1206]"
              style={{ width: `${m.a}%`, background: "var(--oasis-away)" }}
            >
              {m.a.toFixed(1)}%
            </div>
          </div>
          <div className="flex justify-between font-mono text-[10.5px] font-semibold tracking-[0.07em] text-[var(--oasis-text-muted)]">
            <span>{m.home.toUpperCase()} WIN</span>
            <span>DRAW</span>
            <span>{m.away.toUpperCase()} WIN</span>
          </div>
        </div>
        <div className="hidden h-14 w-px self-center bg-[var(--oasis-border)] md:block" />
        <div className="flex flex-wrap gap-6">
          <Stat label="LIKELY SCORE" value={m.score} />
          <Stat label="EXP. GOALS (PROXY)" value={`${m.muHome.toFixed(2)} / ${m.muAway.toFixed(2)}`} />
          <Stat label="O2.5 / BTTS" value={`${matrix.over25} / ${matrix.btts}`} />
          <Stat label="EDGE (HOME)" value={m.edgeLabel} valueColor={m.edge !== null ? "var(--oasis-positive)" : undefined} />
        </div>
      </div>

      <div className="grid grid-cols-1 gap-[14px] lg:grid-cols-[1fr_1fr_320px]">
        <div className="flex flex-col gap-[10px] rounded-[10px] border border-[var(--oasis-border)] bg-[var(--oasis-surface)] p-4">
          <div className="font-mono text-[10px] font-semibold tracking-[0.1em] text-[var(--oasis-text-dim)]">
            SCORE PROBABILITY MATRIX
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

          <div className="mt-1 font-mono text-[10px] font-semibold tracking-[0.1em] text-[var(--oasis-text-dim)]">
            TOTALS &amp; GOALS MARKETS
          </div>
          <div className="flex flex-col gap-[9px] font-mono text-[12px] font-medium">
            <MarketBar label="O 1.5" value={matrix.over15} />
            <MarketBar label="O 2.5" value={matrix.over25} />
            <MarketBar label="O 3.5" value={matrix.over35} />
            <MarketBar label="BTTS" value={matrix.btts} color="var(--oasis-positive)" />
          </div>
        </div>

        <div className="flex flex-col gap-[11px] rounded-[10px] border border-[var(--oasis-border)] bg-[var(--oasis-surface)] p-4">
          <div className="font-mono text-[10px] font-semibold tracking-[0.1em] text-[var(--oasis-text-dim)]">
            WHAT MOVED THIS FORECAST
          </div>
          {m.factors.map((f) => (
            <div key={f.label} className="flex items-center gap-[10px]">
              <span className="w-[132px] text-[12.5px] font-semibold">{f.label}</span>
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
              <span>{m.home}</span>
              <span
                className="font-mono text-[11.5px] font-medium"
                style={{ color: m.missingHome === 0 ? "var(--oasis-positive)" : "var(--oasis-warn)" }}
              >
                {m.missingHome === 0 ? "no reported absences" : `${m.missingHome} out`}
              </span>
            </div>
            <div className="flex justify-between text-[12.5px] font-semibold">
              <span>{m.away}</span>
              <span
                className="font-mono text-[11.5px] font-medium"
                style={{ color: m.missingAway === 0 ? "var(--oasis-positive)" : "var(--oasis-warn)" }}
              >
                {m.missingAway === 0 ? "no reported absences" : `${m.missingAway} out`}
              </span>
            </div>
            <div className="font-mono text-[10.5px] font-medium text-[var(--oasis-text-faint)]">
              injuries updated {utcClock(FRESHNESS.injuries)} UTC · lineups not yet confirmed
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

function Stat({ label, value, valueColor }: { label: string; value: string; valueColor?: string }) {
  return (
    <div>
      <div className="font-mono text-[10px] font-semibold tracking-[0.09em] text-[var(--oasis-text-dim)]">{label}</div>
      <div className="font-mono text-[22px] font-medium" style={{ color: valueColor }}>
        {value}
      </div>
    </div>
  );
}

function MarketBar({ label, value, color = "var(--oasis-home)" }: { label: string; value: number; color?: string }) {
  return (
    <div className="flex items-center gap-[10px]">
      <span className="w-[58px] text-[var(--oasis-text-muted)]">{label}</span>
      <span className="h-2 flex-1 rounded-[4px] bg-[var(--oasis-border-row)]">
        <span className="block h-full rounded-[4px]" style={{ width: `${value}%`, background: color }} />
      </span>
      <span>{value}%</span>
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
