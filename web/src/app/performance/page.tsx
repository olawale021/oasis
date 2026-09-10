import { PerformanceView } from "@/components/performance/performance-view";
import { getLive } from "@/lib/live-server";

export const dynamic = "force-dynamic";

export default async function PerformancePage() {
  return <PerformanceView live={await getLive()} />;
}
