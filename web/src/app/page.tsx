import { HomeConsole } from "@/components/home/home-console";
import { getLive } from "@/lib/live-server";

export const dynamic = "force-dynamic";

export default async function HomePage() {
  return <HomeConsole live={await getLive()} />;
}
