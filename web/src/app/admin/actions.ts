"use server";

import { redirect } from "next/navigation";
import { clearSession, isAdmin, tryLogin } from "@/lib/admin-auth";
import { setPremium } from "@/lib/admin-users";

export async function loginAction(formData: FormData): Promise<void> {
  const password = String(formData.get("password") ?? "");
  const ok = await tryLogin(password);
  redirect(ok ? "/admin" : "/admin?error=1");
}

export async function logoutAction(): Promise<void> {
  await clearSession();
  redirect("/admin");
}

/** Grant or revoke lifetime access. Server Actions are reachable by anyone
 * who can guess the action id, so the gate is re-checked here rather than
 * inherited from the page that rendered the form.
 *
 * The outcome is computed before any redirect: redirect() unwinds by
 * throwing, so calling it inside a try would be caught as a failure. */
export async function setPremiumAction(formData: FormData): Promise<void> {
  if (!(await isAdmin())) redirect("/admin");

  const userId = String(formData.get("userId") ?? "");
  const premium = String(formData.get("premium") ?? "") === "1";
  const note = String(formData.get("note") ?? "").trim() || undefined;
  const query = String(formData.get("query") ?? "");
  const page = String(formData.get("page") ?? "1");

  let result: { key: "userOk" | "userError"; message: string };
  if (!userId.startsWith("user_")) {
    result = { key: "userError", message: "Bad user id." };
  } else {
    try {
      await setPremium(userId, premium, note);
      result = { key: "userOk", message: `${premium ? "Granted" : "Revoked"} lifetime access.` };
    } catch (e) {
      result = { key: "userError", message: e instanceof Error ? e.message : "Update failed." };
    }
  }

  const sp = new URLSearchParams({
    tab: "users",
    ...(query ? { q: query } : {}),
    ...(page !== "1" ? { page } : {}),
    [result.key]: result.message,
  });
  redirect(`/admin?${sp.toString()}`);
}
