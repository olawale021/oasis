import type { Metadata } from "next";
import { hasConfirmedAdult } from "@/app/betting/actions";
import { AdultGate } from "@/components/betting/adult-gate";
import { BettingConsole } from "@/components/betting/betting-console";
import { redactLive } from "@/lib/gate";
import { getLive } from "@/lib/live-server";
import { getViewer } from "@/lib/viewer";

export const dynamic = "force-dynamic";
export const metadata: Metadata = {
  title: "RealscoresAI — Betting",
  description: "Most likely outcomes and where the model disagrees with the bookmakers, by market. Probabilities, not tips.",
};

export default async function BettingPage() {
  // Terms §3: adults only, confirmed once per browser. Checked before any
  // data is fetched so the gate is all an unconfirmed viewer ever receives.
  if (!(await hasConfirmedAdult())) return <AdultGate />;
  const [live, viewer] = await Promise.all([getLive(), getViewer()]);
  // Same gate as the board: upcoming forecasts and their grades are stripped
  // for viewers who may not see them, so the client never holds them.
  return <BettingConsole key={viewer.tier} live={redactLive(live, viewer)} tier={viewer.tier} />;
}
