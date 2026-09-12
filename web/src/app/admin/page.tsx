import type { Metadata } from "next";
import { AdminConsole } from "@/components/admin/admin-console";
import { AdminLogin } from "@/components/admin/admin-login";
import { getAdminSecret, isAdmin } from "@/lib/admin-auth";
import { getLive, getOps } from "@/lib/live-server";
import { nowMs } from "@/lib/ops";

export const dynamic = "force-dynamic";
export const metadata: Metadata = { title: "RealscoreAI — Admin", robots: { index: false, follow: false } };

export default async function AdminPage({ searchParams }: PageProps<"/admin">) {
  if (!(await isAdmin())) {
    const params = await searchParams;
    const configured = (await getAdminSecret()) !== null;
    return <AdminLogin error={params.error === "1"} configured={configured} />;
  }
  const [ops, live] = await Promise.all([getOps(), getLive()]);
  return <AdminConsole ops={ops} liveGeneratedAt={live.generated_at} now={nowMs()} />;
}
