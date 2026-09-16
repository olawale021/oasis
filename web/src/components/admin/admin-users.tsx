import Link from "next/link";
import { setPremiumAction } from "@/app/admin/actions";
import { Card, Empty, Pill, Stat, TABLE, TEXT } from "@/components/admin/ui";
import type { UserPage } from "@/lib/admin-users";
import { ago, stamp } from "@/lib/ops";
import { cn } from "@/lib/utils";

function href(query: string, page: number): string {
  const sp = new URLSearchParams({
    tab: "users",
    ...(query ? { q: query } : {}),
    ...(page !== 1 ? { page: String(page) } : {}),
  });
  return `/admin?${sp.toString()}`;
}

export function AdminUsers({
  data, now, notice,
}: {
  data: UserPage;
  now: number;
  notice: { ok?: string; error?: string };
}) {
  const { users, total, page, pageCount, query, instanceTotal, premiumTotal, premiumExact } = data;
  const premiumLabel = premiumTotal == null ? "—" : premiumExact ? premiumTotal : `${premiumTotal}+`;
  const freeLabel = premiumTotal == null ? "—" : premiumExact ? Math.max(0, instanceTotal - premiumTotal) : "—";

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat k="users" v={instanceTotal.toLocaleString()} sub="registered accounts" />
        <Stat k="lifetime" v={premiumLabel} sub={premiumExact ? "premium access" : "first 1000 scanned"} tone={premiumTotal ? "good" : "plain"} />
        <Stat k="free" v={freeLabel} sub="taster only" />
        <Stat k="showing" v={total.toLocaleString()} sub={query ? `matching “${query}”` : `page ${page} of ${pageCount}`} />
      </div>

      {(notice.ok || notice.error) && (
        <p
          className={cn(
            "rounded-[8px] border px-3 py-[9px] font-sans text-[12.5px]",
            notice.error
              ? "border-[var(--oasis-away)] text-[var(--oasis-away)]"
              : "border-[var(--oasis-positive)] text-[var(--oasis-positive)]",
          )}
        >
          {notice.error ?? notice.ok}
        </p>
      )}

      <Card
        title={query ? `Accounts · ${total} matching` : "Accounts"}
        right={
          <form action="/admin" method="get" className="flex items-center gap-2">
            <input type="hidden" name="tab" value="users" />
            <input
              type="search"
              name="q"
              defaultValue={query}
              placeholder="email, name or user id"
              className="w-[190px] rounded-[6px] border border-[var(--oasis-border-strong)] bg-[var(--oasis-bg)] px-[9px] py-[5px] font-mono text-[11.5px] text-[var(--oasis-text)] outline-none focus:border-[var(--oasis-home)]"
            />
            <button
              type="submit"
              className="rounded-[6px] border border-[var(--oasis-border-strong)] px-[10px] py-[5px] font-sans text-[11.5px] text-[var(--oasis-text-muted)] hover:text-[var(--oasis-text)]"
            >
              Search
            </button>
            {query && (
              <Link href="/admin?tab=users" className="font-sans text-[11.5px] text-[var(--oasis-text-dim)] hover:text-[var(--oasis-text)]">
                clear
              </Link>
            )}
          </form>
        }
        bodyClassName={users.length === 0 || data.error ? "p-4" : "p-0"}
      >
        {data.error ? (
          <p className="rounded-[6px] border border-[var(--oasis-warn)] px-3 py-2 font-sans text-[12.5px] text-[var(--oasis-warn)]">
            Clerk unreachable: {data.error}. Check CLERK_SECRET_KEY is set as a Worker secret.
          </p>
        ) : users.length === 0 ? (
          <Empty>{query ? "No users match that search." : "No users have signed up yet."}</Empty>
        ) : (
          <>
            <div className="overflow-x-auto"><div className="min-w-[820px]">
              <table className="w-full">
                <thead className="bg-[var(--oasis-surface)]">
                  <tr className="border-b border-[var(--oasis-border)]">
                    <th className={TABLE.th}>account</th><th className={TABLE.th}>signed up</th>
                    <th className={TABLE.th}>last seen</th><th className={TABLE.th}>tier</th>
                    <th className={TABLE.th}>last change</th><th className={cn(TABLE.th, "text-right")}>access</th>
                  </tr>
                </thead>
                <tbody>
                  {users.map((u) => (
                    <tr key={u.id} className="border-t border-[var(--oasis-border-row)] hover:bg-[var(--oasis-hover-row)]">
                      <td className="px-2 py-[9px] align-middle">
                        <div className="font-sans text-[12.5px] font-medium text-[var(--oasis-text)]">{u.email}</div>
                        <div className={cn(TEXT.micro, "mt-[2px] truncate")}>
                          {u.name ? <span className="font-sans">{u.name} · </span> : null}
                          {u.id}
                          {u.banned && <span className="ml-[6px] text-[var(--oasis-away)]">banned</span>}
                        </div>
                      </td>
                      <td className={cn(TABLE.td, "whitespace-nowrap text-[11.5px] text-[var(--oasis-text-muted)]")}>
                        {stamp(new Date(u.createdAt).toISOString())}
                      </td>
                      <td className={cn(TABLE.td, "whitespace-nowrap text-[11.5px] text-[var(--oasis-text-muted)]")}>
                        {u.lastSignInAt ? ago(new Date(u.lastSignInAt).toISOString(), now) : "never"}
                      </td>
                      <td className={cn(TABLE.td, "whitespace-nowrap")}>
                        <Pill tone={u.premium ? "good" : "muted"}>{u.premium ? "lifetime" : "free"}</Pill>
                      </td>
                      <td className={cn(TEXT.micro, "max-w-[190px] truncate px-2 py-[9px] align-middle")}>
                        {u.lastChange
                          ? `${u.lastChange.premium ? "granted" : "revoked"} ${ago(u.lastChange.at, now)}${u.lastChange.note ? ` · ${u.lastChange.note}` : ""}`
                          : "—"}
                      </td>
                      <td className="px-2 py-[9px] align-middle">
                        <form action={setPremiumAction} className="flex items-center justify-end gap-[6px]">
                          <input type="hidden" name="userId" value={u.id} />
                          <input type="hidden" name="premium" value={u.premium ? "0" : "1"} />
                          <input type="hidden" name="query" value={query} />
                          <input type="hidden" name="page" value={String(page)} />
                          <input
                            type="text"
                            name="note"
                            placeholder="reason"
                            maxLength={200}
                            className="w-[94px] rounded-[5px] border border-[var(--oasis-border-strong)] bg-[var(--oasis-bg)] px-[7px] py-[4px] font-sans text-[11px] text-[var(--oasis-text)] outline-none focus:border-[var(--oasis-home)]"
                          />
                          <button
                            type="submit"
                            className={cn(
                              "rounded-[5px] px-[10px] py-[5px] font-sans text-[11.5px] font-semibold transition-colors",
                              u.premium
                                ? "border border-[var(--oasis-border-strong)] text-[var(--oasis-text-muted)] hover:border-[var(--oasis-away)] hover:text-[var(--oasis-away)]"
                                : "bg-[var(--oasis-home)] text-[var(--oasis-home-ink)] hover:opacity-90",
                            )}
                          >
                            {u.premium ? "Revoke" : "Grant"}
                          </button>
                        </form>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div></div>

            {pageCount > 1 && (
              <div className="flex items-center justify-between border-t border-[var(--oasis-border)] px-4 py-[10px]">
                <span className={TEXT.micro}>page {page} of {pageCount}</span>
                <span className="flex gap-3 font-sans text-[11.5px]">
                  {page > 1 && <Link href={href(query, page - 1)} className="text-[var(--oasis-text-muted)] hover:text-[var(--oasis-text)]">← prev</Link>}
                  {page < pageCount && <Link href={href(query, page + 1)} className="text-[var(--oasis-text-muted)] hover:text-[var(--oasis-text)]">next →</Link>}
                </span>
              </div>
            )}
          </>
        )}
      </Card>

      <p className={cn(TEXT.micro, "text-[var(--oasis-text-faint)]")}>
        Premium is a flag in Clerk public metadata, read from the session token. A change reaches the user when
        their token next refreshes — up to about a minute, or immediately if they sign out and back in. Reasons
        are stored in private metadata, which the user cannot see.
      </p>
    </div>
  );
}
