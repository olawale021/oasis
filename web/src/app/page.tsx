import { HomeConsole } from "@/components/home/home-console";
import { getLive } from "@/lib/live-server";
import { getViewer } from "@/lib/viewer";
import { redactLive } from "@/lib/gate";

export const dynamic = "force-dynamic";

export default async function HomePage() {
  const [live, viewer] = await Promise.all([getLive(), getViewer()]);
  return <HomeConsole live={redactLive(live, viewer)} tier={viewer.tier} />;
}
