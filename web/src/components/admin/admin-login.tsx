import { loginAction } from "@/app/admin/actions";

export function AdminLogin({ error, configured }: { error: boolean; configured: boolean }) {
  return (
    <div className="flex min-h-[70vh] items-center justify-center px-4">
      <form
        action={loginAction}
        className="w-full max-w-[340px] rounded-[10px] border border-[var(--oasis-border)] bg-[var(--oasis-surface)] p-6"
      >
        <div className="mb-1 font-sans text-[15px] font-extrabold">Operator sign-in</div>
        <p className="mb-5 text-[12.5px] text-[var(--oasis-text-muted)]">
          Pipeline monitoring for the matchday server.
        </p>
        {!configured && (
          <p className="mb-4 rounded-[6px] border border-[var(--oasis-warn)] px-3 py-2 font-mono text-[11.5px] text-[var(--oasis-warn)]">
            ADMIN_PASSWORD is not set on this deployment.
          </p>
        )}
        <label className="mb-1 block font-mono text-[11px] uppercase tracking-[0.06em] text-[var(--oasis-text-dim)]">
          Password
        </label>
        <input
          type="password"
          name="password"
          autoComplete="current-password"
          autoFocus
          required
          className="mb-3 w-full rounded-[7px] border border-[var(--oasis-border-strong)] bg-[var(--oasis-bg)] px-3 py-2 font-mono text-[13px] text-[var(--oasis-text)] outline-none focus:border-[var(--oasis-home)]"
        />
        {error && (
          <p className="mb-3 font-mono text-[11.5px] text-[var(--oasis-away)]">Wrong password.</p>
        )}
        <button
          type="submit"
          className="w-full rounded-[7px] bg-[var(--oasis-home)] py-2 text-[12.5px] font-bold text-[var(--oasis-home-ink)]"
        >
          Sign in
        </button>
      </form>
    </div>
  );
}
