import type { Metadata } from "next";
import { AdminShell } from "@/components/admin/admin-console";
import { AdminLogin } from "@/components/admin/admin-login";
import { AdminUsers } from "@/components/admin/admin-users";
import { TabLedger } from "@/components/admin/tab-ledger";
import { TabLogs } from "@/components/admin/tab-logs";
import { TabOverview } from "@/components/admin/tab-overview";
import { TabPipeline } from "@/components/admin/tab-pipeline";
import { getAdminSecret, isAdmin } from "@/lib/admin-auth";
import { parseTab } from "@/lib/admin-tabs";
import { listUsers } from "@/lib/admin-users";
import { getLive, getOps } from "@/lib/live-server";
import { nowMs } from "@/lib/ops";

export const dynamic = "force-dynamic";
export const metadata: Metadata = { title: "RealscoresAI — Admin", robots: { index: false, follow: false } };

const one = (v: string | string[] | undefined): string => (Array.isArray(v) ? (v[0] ?? "") : (v ?? ""));

export default async function AdminPage({ searchParams }: PageProps<"/admin">) {
  const params = await searchParams;
  if (!(await isAdmin())) {
    const configured = (await getAdminSecret()) !== null;
    return <AdminLogin error={one(params.error) === "1"} configured={configured} />;
  }

  const tab = parseTab(one(params.tab) || undefined);
  const query = one(params.q);
  const page = Math.max(1, Number.parseInt(one(params.page), 10) || 1);

  // Only the Users tab pays for the Clerk round-trips.
  const [ops, live, users] = await Promise.all([
    getOps(),
    getLive(),
    tab === "users" ? listUsers(query, page) : Promise.resolve(null),
  ]);
  const now = nowMs();

  return (
    <AdminShell ops={ops} liveGeneratedAt={live.generated_at} now={now} tab={tab}>
      {tab === "overview" && <TabOverview ops={ops} now={now} />}
      {tab === "users" && users && (
        <AdminUsers
          data={users}
          now={now}
          notice={{ ok: one(params.userOk) || undefined, error: one(params.userError) || undefined }}
        />
      )}
      {tab === "pipeline" && <TabPipeline ops={ops} now={now} />}
      {tab === "ledger" && <TabLedger ops={ops} />}
      {tab === "logs" && <TabLogs ops={ops} />}
    </AdminShell>
  );
}
