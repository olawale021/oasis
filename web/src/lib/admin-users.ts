import "server-only";
import { clerkClient } from "@clerk/nextjs/server";

/** User administration for /admin. Premium is a boolean in Clerk public
 * metadata; `getViewer()` reads it off the session claims, so a change here
 * reaches the user on their next token refresh (~60s), not instantly.
 *
 * Every grant/revoke appends to `privateMetadata.access_log` — backend-only,
 * invisible to the user — so a comped or refunded account carries its own
 * paper trail. The console is a single shared password, so the log records
 * what happened and when, not which human did it. */

export const USERS_PAGE_SIZE = 25;

export interface AdminUser {
  id: string;
  email: string;
  name: string | null;
  premium: boolean;
  createdAt: number;
  lastSignInAt: number | null;
  banned: boolean;
  /** Most recent access-log entry, when the flag was set from this console. */
  lastChange: AccessLogEntry | null;
}

export interface AccessLogEntry {
  at: string;
  premium: boolean;
  note?: string;
}

export interface UserPage {
  users: AdminUser[];
  /** Users matching the current search — drives pagination. */
  total: number;
  page: number;
  pageCount: number;
  query: string;
  /** Instance-wide counts, independent of the search box. */
  instanceTotal: number;
  premiumTotal: number | null;
  /** False when the premium scan hit its cap, so the count is a floor. */
  premiumExact: boolean;
  /** Set when Clerk could not be reached (missing key, network, bad key). */
  error: string | null;
}

const MAX_LOG = 20;
/** Clerk cannot filter users by metadata, so a premium count means walking
 * the list. Capped so a large instance degrades to "at least N" rather than
 * hammering the API on every page view. */
const SCAN_PAGE = 100;
const SCAN_MAX_PAGES = 10;

function readLog(priv: unknown): AccessLogEntry[] {
  const raw = (priv as { access_log?: unknown } | null)?.access_log;
  if (!Array.isArray(raw)) return [];
  return raw.filter(
    (e): e is AccessLogEntry =>
      typeof e === "object" && e !== null && typeof (e as AccessLogEntry).at === "string",
  );
}

async function countPremium(
  client: Awaited<ReturnType<typeof clerkClient>>,
  instanceTotal: number,
): Promise<{ count: number; exact: boolean }> {
  let count = 0;
  let seen = 0;
  for (let i = 0; i < SCAN_MAX_PAGES; i++) {
    const { data } = await client.users.getUserList({ limit: SCAN_PAGE, offset: i * SCAN_PAGE });
    count += data.filter((u) => (u.publicMetadata as { premium?: boolean } | null)?.premium === true).length;
    seen += data.length;
    if (data.length < SCAN_PAGE || seen >= instanceTotal) return { count, exact: true };
  }
  return { count, exact: false };
}

export async function listUsers(query: string, page: number): Promise<UserPage> {
  const q = query.trim();
  const p = Number.isFinite(page) && page > 0 ? Math.floor(page) : 1;
  try {
    const client = await clerkClient();
    const [{ data, totalCount }, instanceTotal] = await Promise.all([
      client.users.getUserList({
        limit: USERS_PAGE_SIZE,
        offset: (p - 1) * USERS_PAGE_SIZE,
        orderBy: "-created_at",
        ...(q ? { query: q } : {}),
      }),
      q ? client.users.getCount() : Promise.resolve(-1),
    ]);
    const total = instanceTotal === -1 ? totalCount : instanceTotal;
    const premium = await countPremium(client, total);
    return {
      users: data.map((u) => {
        const log = readLog(u.privateMetadata);
        const name = [u.firstName, u.lastName].filter(Boolean).join(" ");
        return {
          id: u.id,
          email: u.primaryEmailAddress?.emailAddress ?? u.emailAddresses[0]?.emailAddress ?? "—",
          name: name || null,
          premium: (u.publicMetadata as { premium?: boolean } | null)?.premium === true,
          createdAt: u.createdAt,
          lastSignInAt: u.lastSignInAt,
          banned: u.banned,
          lastChange: log.length > 0 ? log[log.length - 1] : null,
        };
      }),
      total: totalCount,
      page: p,
      pageCount: Math.max(1, Math.ceil(totalCount / USERS_PAGE_SIZE)),
      query: q,
      instanceTotal: total,
      premiumTotal: premium.count,
      premiumExact: premium.exact,
      error: null,
    };
  } catch (e) {
    return {
      users: [], total: 0, page: p, pageCount: 1, query: q,
      instanceTotal: 0, premiumTotal: null, premiumExact: false,
      error: e instanceof Error ? e.message : "Clerk request failed",
    };
  }
}

/** Flips the premium flag and appends an audit entry. Throws on failure so
 * the caller can surface the reason rather than silently no-op. */
export async function setPremium(userId: string, premium: boolean, note?: string): Promise<void> {
  const client = await clerkClient();
  const user = await client.users.getUser(userId);
  const entry: AccessLogEntry = {
    at: new Date().toISOString(),
    premium,
    ...(note ? { note: note.slice(0, 200) } : {}),
  };
  const log = [...readLog(user.privateMetadata), entry].slice(-MAX_LOG);
  // updateUserMetadata deep-merges, so untouched keys in either bag survive.
  await client.users.updateUserMetadata(userId, {
    publicMetadata: { premium },
    privateMetadata: { access_log: log },
  });
}
