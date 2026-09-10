import { EditorialConsole } from "@/components/home/editorial-console";
import { getLive } from "@/lib/live-server";

export const dynamic = "force-dynamic";

export default async function HomeEditorialPage() {
  return <EditorialConsole live={await getLive()} />;
}
