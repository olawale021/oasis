import { EditorialConsole } from "@/components/home/editorial-console";
import { getLive } from "@/lib/live-server";
import { getViewer } from "@/lib/viewer";
import { redactLive } from "@/lib/gate";

export const dynamic = "force-dynamic";

export default async function HomeEditorialPage() {
  const [live, viewer] = await Promise.all([getLive(), getViewer()]);
  return <EditorialConsole live={redactLive(live, viewer)} />;
}
