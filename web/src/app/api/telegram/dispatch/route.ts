import { makeSender } from "@/lib/telegram/api";
import { buildDispatch, subscribers, type DispatchEvent } from "@/lib/telegram/bot";
import { tgEnv } from "@/lib/telegram/env";
import { getLive } from "@/lib/live-server";

export const dynamic = "force-dynamic";

/** Matchday chain → us, after each KV push: "these fixtures locked / went
 * final / settled", or "it's digest time". Sends a window of at most
 * `BATCH` messages per call (Workers cap outbound fetches per request)
 * and returns `next` so the caller loops. Idempotence is the caller's:
 * the chain tracks what it has already announced. */
const BATCH = 40;

export async function POST(req: Request): Promise<Response> {
  const env = await tgEnv();
  const auth = req.headers.get("authorization") ?? "";
  if (!env.dispatchSecret || auth !== `Bearer ${env.dispatchSecret}`) {
    return new Response("forbidden", { status: 403 });
  }
  let body: { events?: DispatchEvent[]; cursor?: number; dry?: boolean };
  try {
    body = (await req.json()) as typeof body;
  } catch {
    return new Response("bad request", { status: 400 });
  }
  const events = (body.events ?? []).filter((e) => ["digest", "lock", "final", "settled"].includes(e.type));
  if (events.length === 0) return Response.json({ total: 0, sent: 0, next: null });

  const [live, subs] = await Promise.all([getLive(), subscribers(env.kv)]);
  const all = buildDispatch(live, subs, events);
  const cursor = Math.max(0, body.cursor ?? 0);
  const window = all.slice(cursor, cursor + BATCH);
  const sender = makeSender(body.dry ? null : env.token);
  let sent = 0;
  const errors: string[] = [];
  for (const m of window) {
    try {
      await sender.send(m);
      sent += 1;
    } catch (e) {
      errors.push(e instanceof Error ? e.message : String(e));
    }
  }
  const next = cursor + BATCH < all.length ? cursor + BATCH : null;
  return Response.json({
    total: all.length, subscribers: subs.length, sent, next, errors: errors.slice(0, 5),
    ...(sender.dry ? { dry: sender.sent.map((m) => ({ chat_id: m.chat_id, text: m.text.slice(0, 160) })) } : {}),
  });
}
