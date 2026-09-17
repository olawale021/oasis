import { makeSender } from "@/lib/telegram/api";
import { handleUpdate } from "@/lib/telegram/bot";
import { tgEnv } from "@/lib/telegram/env";
import { getLive } from "@/lib/live-server";

export const dynamic = "force-dynamic";

/** Telegram → us. The secret token is set with setWebhook and arrives on
 * every call; without it configured (dev) the route answers in dry mode
 * and echoes what it would have sent, so the flows can be curl-tested. */
export async function POST(req: Request): Promise<Response> {
  const env = await tgEnv();
  if (env.webhookSecret && req.headers.get("x-telegram-bot-api-secret-token") !== env.webhookSecret) {
    return new Response("forbidden", { status: 403 });
  }
  let update: Record<string, unknown>;
  try {
    update = (await req.json()) as Record<string, unknown>;
  } catch {
    return new Response("bad request", { status: 400 });
  }
  const sender = makeSender(env.token);
  try {
    await handleUpdate(update, { env, sender, live: await getLive() });
  } catch (e) {
    // Always 200 to Telegram: a 5xx makes it retry the same update for hours.
    console.error("[telegram webhook]", e);
    return Response.json({ ok: false, error: e instanceof Error ? e.message : String(e) });
  }
  return Response.json(sender.dry ? { ok: true, dry: sender.sent } : { ok: true });
}
