import { clerkMiddleware, createRouteMatcher } from "@clerk/nextjs/server";

/** Deliberately named middleware.ts, not proxy.ts: Next 16's proxy.ts runs
 * on the Node runtime, which @opennextjs/cloudflare does not support yet
 * ("Node.js middleware is not currently supported"). The deprecated
 * middleware.ts convention still compiles to edge middleware, which the
 * Worker build accepts. Rename once OpenNext supports Node proxies.
 *
 * Everything is public except the account area. Gating of prediction
 * fields happens in server components via `getViewer()`, not here. */
const isProtected = createRouteMatcher(["/account(.*)"]);

export default clerkMiddleware(async (auth, req) => {
  if (isProtected(req)) await auth.protect();
});

export const config = {
  matcher: [
    // Skip Next internals and static files unless in search params.
    "/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)",
    // Always run for API routes.
    "/(api|trpc)(.*)",
  ],
};
