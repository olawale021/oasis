"use server";

import { redirect } from "next/navigation";
import { clearSession, tryLogin } from "@/lib/admin-auth";

export async function loginAction(formData: FormData): Promise<void> {
  const password = String(formData.get("password") ?? "");
  const ok = await tryLogin(password);
  redirect(ok ? "/admin" : "/admin?error=1");
}

export async function logoutAction(): Promise<void> {
  await clearSession();
  redirect("/admin");
}
