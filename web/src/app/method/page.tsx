import type { Metadata } from "next";
import Link from "next/link";
import { getLive } from "@/lib/live-server";

export const dynamic = "force-dynamic";
export const metadata: Metadata = {
  title: "RealscoresAI — Method",
  description: "How the RealscoresAI forecasts are built, tested and published.",
};

/** One numbered step: the label sits in a narrow left column so the eye can
 * scan the sequence, the prose takes the rest. Rules, not boxes, divide
 * steps. */
function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="grid gap-3 border-t border-[var(--oasis-border)] pt-5 sm:grid-cols-[160px_1fr] sm:gap-8">
      <h2 className="font-mono text-label font-semibold uppercase text-[var(--oasis-text-dim)] sm:pt-[3px]">{title}</h2>
      <div className="flex max-w-[68ch] flex-col gap-3 text-body text-[var(--oasis-text-soft)]">{children}</div>
    </section>
  );
}

export default async function MethodPage() {
  const live = await getLive();
  const versions = Object.entries(live.model_versions);
  return (
    <div className="mx-auto flex w-full max-w-[860px] flex-col gap-6 p-4 pb-12 sm:p-6">
      <div className="flex flex-col gap-3 pb-2 sm:pr-[20%]">
        <span className="font-mono text-label font-semibold uppercase text-[var(--oasis-text-dim)]">Method</span>
        <h1 className="text-display font-extrabold">How the forecasts are made</h1>
        <p className="max-w-[62ch] text-lead text-[var(--oasis-text-muted)]">
          RealscoresAI publishes calibrated pre-match probabilities for five leagues. Every number on the site comes from the same
          pipeline described here, is tested on seasons the model never saw, and is frozen before kickoff so it can be
          judged afterwards. Probabilistic forecasts, not betting advice.
        </p>
      </div>

      <Section title="1 · Data">
        <p>
          Results, fixtures, injuries, confirmed lineups, match statistics and bookmaker odds come from API-Football,
          from 2017 onwards for the Premier League, La Liga, Serie A, Bundesliga and MLS, plus the second divisions so
          promoted clubs arrive with history. Fixtures in every competition, including cups and European ties, are
          pulled per club so rest and congestion see midweek games. Squad market values come from the public
          Transfermarkt datasets and are computed as of each kickoff, so no later valuation leaks in.
        </p>
      </Section>

      <Section title="2 · Features">
        <p>
          Each match is described by differences between the two sides, all computed strictly from matches before it:
          Elo with margin of victory and home advantage; recency-weighted form, goals for and against; head-to-head
          history; rest days and congestion; venue form; rating momentum and schedule strength; learned pi and Berrar
          ratings; reported absences; shots, possession and expected goals where statistics exist; the log ratio of
          squad market values; and, in the Premier League, the summed plus-minus ratings of each side&apos;s expected
          eleven from lineup history.
        </p>
      </Section>

      <Section title="3 · Models">
        <p>
          The outcome probabilities are a weighted blend of two multinomial logistic regressions per league: one fit on
          that league alone, one pooled across all five with league indicators, each with season decay and a
          temperature fitted on a held-out season. In La Liga a random forest on the same features takes part of the
          weight. Scorelines, over 2.5 and both-teams-score come from a separate Dixon-Coles Poisson model. The linear
          models are what let each match page show which factors moved the forecast.
        </p>
        <p className="font-mono text-meta text-[var(--oasis-text-muted)]">
          Serving now:{" "}
          {versions.map(([lg, v], i) => (
            <span key={lg}>
              {lg} {v}
              {i < versions.length - 1 ? " · " : ""}
            </span>
          ))}
        </p>
      </Section>

      <Section title="4 · How candidates earn a place">
        <p>
          Every feature, learner or blend weight is judged on a walk-forward harness: refit on earlier seasons only and
          scored on each of five held-out test seasons, 2021 to 2025. The decision metric is mean log loss across the
          folds, because it rewards being right with the right confidence, and a candidate ships only if it improves
          that mean by at least 0.001. A single good season does not count. Ideas that failed are kept on the{" "}
          <Link href="/performance" className="font-semibold text-[var(--oasis-home)]">
            Experiments tab
          </Link>{" "}
          so they are not retried without new data.
        </p>
      </Section>

      <Section title="5 · Locking and the live record">
        <p>
          Predictions regenerate hourly, but the one that counts is frozen about seventy minutes before kickoff, with
          the bookmaker consensus at that moment stored beside it. After full time the result is settled against that
          frozen forecast and nothing is edited. The live record on the performance page is built only from these
          locked rows; the backtest numbers there come from the held-out 2025/26 season and are shown separately.
        </p>
      </Section>

      <Section title="6 · Odds">
        <p>
          Bookmaker odds are collected in windows before each match, margin removed, and used as a benchmark and for the
          edge column. They are never a model input. That is a deliberate choice: a model that reads the market cannot
          tell you anything the market does not already say.
        </p>
      </Section>
    </div>
  );
}
