"use server";

import { cookies } from "next/headers";
import { redirect } from "next/navigation";

/** Terms §3: "The Betting section is for adults only; by opening it you
 * confirm you meet this requirement." This is that confirmation. A plain
 * cookie, not an account flag: it has to work for anonymous viewers, and
 * it is a statement by the person at the browser, not a fact about the
 * account. One year, then asked again. */
export const ADULT_COOKIE = "rs_adult";

export async function confirmAdultAction(): Promise<void> {
  (await cookies()).set(ADULT_COOKIE, "1", {
    httpOnly: true, secure: true, sameSite: "lax", path: "/", maxAge: 60 * 60 * 24 * 365,
  });
  redirect("/betting");
}

export async function hasConfirmedAdult(): Promise<boolean> {
  return (await cookies()).get(ADULT_COOKIE)?.value === "1";
}
