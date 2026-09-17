import "server-only";

/** The slice of the Bot API we use. `makeSender(null)` is a dry sender that
 * records what it would have sent -- used in dev and by the routes' test
 * mode, so the flows can be exercised without a bot token. */

export interface Outgoing {
  chat_id: number | string;
  text: string;
  reply_markup?: unknown;
}

export interface Sender {
  send(msg: Outgoing): Promise<void>;
  answerCallback(id: string, text?: string): Promise<void>;
  editMarkup(chat_id: number, message_id: number, reply_markup: unknown): Promise<void>;
  readonly sent: Outgoing[];
  readonly dry: boolean;
}

const MAX_TEXT = 4000;

/** Telegram caps a message at 4096 chars; split on line boundaries. */
export function chunkText(text: string): string[] {
  if (text.length <= MAX_TEXT) return [text];
  const out: string[] = [];
  let cur = "";
  for (const line of text.split("\n")) {
    if (cur.length + line.length + 1 > MAX_TEXT) {
      out.push(cur);
      cur = line;
    } else {
      cur = cur ? `${cur}\n${line}` : line;
    }
  }
  if (cur) out.push(cur);
  return out;
}

export function makeSender(token: string | null): Sender {
  const sent: Outgoing[] = [];
  const call = async (method: string, body: unknown): Promise<void> => {
    if (!token) return;
    const res = await fetch(`https://api.telegram.org/bot${token}/${method}`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      const detail = await res.text().catch(() => "");
      // 403 = user blocked the bot; not our error, and not worth failing a batch.
      if (res.status !== 403) throw new Error(`telegram ${method} ${res.status}: ${detail.slice(0, 200)}`);
    }
  };
  return {
    sent,
    dry: !token,
    async send(msg) {
      const parts = chunkText(msg.text);
      for (let i = 0; i < parts.length; i++) {
        const m: Outgoing = { ...msg, text: parts[i], reply_markup: i === parts.length - 1 ? msg.reply_markup : undefined };
        sent.push(m);
        await call("sendMessage", { ...m, parse_mode: "HTML", disable_web_page_preview: true });
      }
    },
    async answerCallback(id, text) {
      await call("answerCallbackQuery", { callback_query_id: id, text });
    },
    async editMarkup(chat_id, message_id, reply_markup) {
      await call("editMessageReplyMarkup", { chat_id, message_id, reply_markup });
    },
  };
}
