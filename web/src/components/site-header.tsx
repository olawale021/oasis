"use client";

import { useState } from "react";
import Link from "next/link";
import { Show, SignInButton, UserButton } from "@clerk/nextjs";
import { usePathname } from "next/navigation";
import { utcClock } from "@/lib/data";
import { cn } from "@/lib/utils";
import { Logo } from "@/components/logo";
import { ThemeToggle } from "@/components/theme-toggle";

const NAV_LINKS = [
  { label: "Today", href: "/", match: (p: string) => p === "/" },
  { label: "Leagues", href: "/league/EPL", match: (p: string) => p.startsWith("/league") },
  { label: "Performance", href: "/performance", match: (p: string) => p.startsWith("/performance") },
  { label: "Method", href: "/method", match: (p: string) => p.startsWith("/method") },
];

const ICON = {
  today: <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><rect x="2" y="3" width="12" height="11" rx="2" /><path d="M2 7h12M5.5 1.5v3M10.5 1.5v3" /></svg>,
  leagues: <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M4 2h8v3a4 4 0 0 1-8 0V2zM12 3h2v1.5a2.5 2.5 0 0 1-2 2.45M4 3H2v1.5a2.5 2.5 0 0 0 2 2.45M8 9v3M5.5 14h5" /></svg>,
  performance: <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M2 13h12M3.5 10.5l3-3 2.5 2.5 4-4.5" /><path d="M10.5 5.5H13V8" /></svg>,
  method: <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M3 2.5h10v11H3z" /><path d="M5.5 5.5h5M5.5 8h5M5.5 10.5h3" /></svg>,
  pricing: <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M2 8.5V3.5A1.5 1.5 0 0 1 3.5 2h5L14 7.5 8.5 13 2 8.5z" /><circle cx="5.5" cy="5.5" r="1" /></svg>,
};

const MENU = [
  { label: "Today", href: "/", hint: "settled results and the upcoming board", icon: ICON.today, match: (p: string) => p === "/" },
  { label: "Leagues", href: "/league/EPL", hint: "fixtures and standings by league", icon: ICON.leagues, match: (p: string) => p.startsWith("/league") },
  { label: "Performance", href: "/performance", hint: "the full locked record and backtests", icon: ICON.performance, match: (p: string) => p.startsWith("/performance") },
  { label: "Method", href: "/method", hint: "how forecasts are built and scored", icon: ICON.method, match: (p: string) => p.startsWith("/method") },
  { label: "Pricing", href: "/pricing", hint: "founding-member lifetime access", icon: ICON.pricing, match: (p: string) => p.startsWith("/pricing") },
];

export function SiteHeader({ generatedAt }: { generatedAt: string }) {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);

  return (
    <header className="relative z-40 border-b border-[var(--oasis-border)] bg-[var(--oasis-surface)]">
      <div className="relative z-50 flex w-full items-center gap-4 bg-[var(--oasis-surface)] px-4 py-3 sm:gap-[26px] sm:px-[22px] sm:py-[14px]">
        <Link href="/" className="flex items-center" aria-label="RealscoresAI home">
          <Logo size={19} />
        </Link>

        <nav className="hidden items-center gap-5 text-[13.5px] font-semibold sm:flex md:absolute md:left-1/2 md:-translate-x-1/2">
          {NAV_LINKS.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className={cn(
                "transition-colors",
                link.match(pathname ?? "")
                  ? "text-[var(--oasis-text)]"
                  : "text-[var(--oasis-text-muted)] hover:text-[var(--oasis-text)]",
              )}
            >
              {link.label}
            </Link>
          ))}
          <span className="cursor-default text-[var(--oasis-text-muted)]">Pricing</span>
        </nav>

        <div className="ml-auto flex items-center gap-3">
          <span className="hidden items-center gap-[6px] font-mono text-[11.5px] font-medium text-[var(--oasis-text-dim)] md:flex">
            <span className="rs-live-dot h-[6px] w-[6px] rounded-full bg-[var(--oasis-positive)]" />
            data {utcClock(generatedAt)} UTC
          </span>
          <Link
            href="/pricing"
            className="rs-cta whitespace-nowrap rounded-[7px] bg-[var(--oasis-home)] px-[11px] py-[6px] text-[11.5px] font-bold text-[var(--oasis-home-ink)] sm:px-[13px] sm:py-[7px] sm:text-[12.5px]"
          >
            <span className="sm:hidden">Lifetime access</span>
            <span className="hidden sm:inline">Get lifetime access</span>
          </Link>
          <Show when="signed-out">
            <SignInButton mode="modal">
              <button
                type="button"
                className="rs-cta hidden whitespace-nowrap rounded-[7px] border border-[var(--oasis-border-strong)] px-[11px] py-[6px] text-[11.5px] font-semibold text-[var(--oasis-text-soft)] hover:text-[var(--oasis-text)] sm:inline-block sm:px-[13px] sm:py-[7px] sm:text-[12.5px]"
              >
                Sign in
              </button>
            </SignInButton>
          </Show>
          <Show when="signed-in">
            <UserButton />
          </Show>
          <ThemeToggle className="hidden sm:flex" />
          <button
            type="button"
            aria-label={open ? "Close menu" : "Open menu"}
            aria-expanded={open}
            onClick={() => setOpen((v) => !v)}
            className="flex h-8 w-8 items-center justify-center rounded-[7px] border border-[var(--oasis-border-strong)] text-[var(--oasis-text-soft)] sm:hidden"
          >
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
              {open ? (
                <><path d="M3 3l10 10" /><path d="M13 3L3 13" /></>
              ) : (
                <><path d="M2 4h12" /><path d="M2 8h12" /><path d="M2 12h12" /></>
              )}
            </svg>
          </button>
        </div>
      </div>

      {open && (
        <div className="sm:hidden">
          <button
            type="button"
            aria-label="Close menu"
            onClick={() => setOpen(false)}
            className="rs-fade-in fixed inset-0 z-30 bg-[rgba(8,11,16,.72)] backdrop-blur-[2px]"
          />
          <nav className="rs-sheet absolute inset-x-0 top-full z-40 border-b border-[var(--oasis-border)] bg-[var(--oasis-surface)] shadow-[0_24px_48px_rgba(0,0,0,.55)]">
            <div className="flex flex-col px-4 pt-2">
              {MENU.map((item, i) => {
                const active = item.match(pathname ?? "");
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    onClick={() => setOpen(false)}
                    className="rs-rise flex items-center gap-[14px] border-b border-[var(--oasis-border-row)] py-[13px] last:border-0"
                    style={{ animationDelay: `${40 + i * 45}ms` }}
                  >
                    <span
                      className="flex h-9 w-9 shrink-0 items-center justify-center rounded-[9px] border"
                      style={{
                        borderColor: active ? "var(--oasis-home)" : "var(--oasis-border-strong)",
                        background: active ? "var(--oasis-home-tint)" : "var(--oasis-surface-raised)",
                        color: active ? "var(--oasis-home)" : "var(--oasis-text-soft)",
                      }}
                    >
                      {item.icon}
                    </span>
                    <span className="flex min-w-0 flex-col gap-[2px]">
                      <span className="text-[15px] font-bold tracking-[-0.01em]" style={{ color: active ? "var(--oasis-text)" : "var(--oasis-text-soft)" }}>
                        {item.label}
                      </span>
                      <span className="font-mono text-[10.5px] font-medium text-[var(--oasis-text-dim)]">{item.hint}</span>
                    </span>
                    <svg className="ml-auto shrink-0 text-[var(--oasis-text-faint)]" width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><path d="M6 3l5 5-5 5" /></svg>
                  </Link>
                );
              })}
            </div>
            <div className="rs-rise flex items-center gap-[10px] border-t border-[var(--oasis-border)] px-4 py-3" style={{ animationDelay: "300ms" }}>
              <Show when="signed-out">
                <SignInButton mode="modal">
                  <button type="button" className="rs-cta flex-1 rounded-[8px] border border-[var(--oasis-border-strong)] py-[10px] text-[13px] font-semibold text-[var(--oasis-text-soft)]">
                    Sign in
                  </button>
                </SignInButton>
              </Show>
              <Show when="signed-in">
                <Link href="/account" onClick={() => setOpen(false)} className="rs-cta flex-1 rounded-[8px] border border-[var(--oasis-border-strong)] py-[10px] text-center text-[13px] font-semibold text-[var(--oasis-text-soft)]">
                  Account
                </Link>
              </Show>
              <Link href="/pricing" onClick={() => setOpen(false)} className="rs-cta flex-1 rounded-[8px] bg-[var(--oasis-home)] py-[10px] text-center text-[13px] font-bold text-[var(--oasis-home-ink)]">
                Get lifetime access
              </Link>
            </div>
            <div className="flex items-center justify-between gap-3 px-4 pb-3 font-mono text-[10.5px] font-medium text-[var(--oasis-text-dim)]">
              <span className="flex items-center gap-[6px]"><span className="rs-live-dot h-[6px] w-[6px] rounded-full bg-[var(--oasis-positive)]" />data {utcClock(generatedAt)} UTC</span>
              <span className="flex items-center gap-3">
                <Link href="/privacy" onClick={() => setOpen(false)} className="text-[var(--oasis-text-muted)]">Privacy</Link>
                <Link href="/terms" onClick={() => setOpen(false)} className="text-[var(--oasis-text-muted)]">Terms</Link>
                <ThemeToggle />
              </span>
            </div>
          </nav>
        </div>
      )}
    </header>
  );
}
