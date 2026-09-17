import { HomeConsole } from "@/components/home/home-console";
import { getLive } from "@/lib/live-server";
import { getViewer } from "@/lib/viewer";
import { redactLive } from "@/lib/gate";

export const dynamic = "force-dynamic";

export default async function HomePage() {
  const [live, viewer] = await Promise.all([getLive(), getViewer()]);
  // Keyed by tier: HomeConsole picks its landing tab from tier at mount,
  // so a tier change has to remount it or a signed-out viewer is stranded on
  // "Week" -- a tab whose buttons are hidden for anon and whose rows are all
  // redacted, with no way back to Results.
  return <HomeConsole key={viewer.tier} live={redactLive(live, viewer)} tier={viewer.tier} />;
}
