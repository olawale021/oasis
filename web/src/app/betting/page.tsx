import type { Metadata } from "next";
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
  const [live, viewer] = await Promise.all([getLive(), getViewer()]);
  // Same gate as the board: upcoming forecasts and their grades are stripped
  // for viewers who may not see them, so the client never holds them.
  return <BettingConsole key={viewer.tier} live={redactLive(live, viewer)} tier={viewer.tier} />;
}
