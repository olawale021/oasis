/** Tabs are URL state, not client state: each one is a plain link to
 * /admin?tab=…, so the page stays a server component, every view is
 * deep-linkable, and a refresh keeps you where you were. */

export const TABS = [
  { id: "overview", label: "Overview" },
  { id: "users", label: "Users" },
  { id: "pipeline", label: "Pipeline" },
  { id: "ledger", label: "Ledger" },
  { id: "logs", label: "Logs" },
] as const;

export type TabId = (typeof TABS)[number]["id"];

export function parseTab(v: string | undefined): TabId {
  return TABS.some((t) => t.id === v) ? (v as TabId) : "overview";
}
