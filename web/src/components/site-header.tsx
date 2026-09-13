"use client";

import { useState } from "react";
import Link from "next/link";
import { Show, SignInButton, UserButton } from "@clerk/nextjs";
import { usePathname } from "next/navigation";
import { utcClock } from "@/lib/data";
import { cn } from "@/lib/utils";

const NAV_LINKS = [
  { label: "Today", href: "/", match: (p: string) => p === "/" },
  { label: "Leagues", href: "/league/EPL", match: (p: string) => p.startsWith("/league") },
  { label: "Performance", href: "/performance", match: (p: string) => p.startsWith("/performance") },
  { label: "Method", href: "/method", match: (p: string) => p.startsWith("/method") },
];

export function SiteHeader({ generatedAt }: { generatedAt: string }) {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);

  return (
    <header className="border-b border-[var(--oasis-border)] bg-[var(--oasis-surface)]">
      <div className="flex w-full items-center gap-4 px-4 py-3 sm:gap-[26px] sm:px-[22px] sm:py-[14px]">
        <Link href="/" className="flex items-center gap-[9px]">
          <span
            className="block h-[22px] w-[22px] rounded-[6px]"
            style={{ background: "linear-gradient(140deg,#4d9cf6,#2fcf9a)" }}
          />
          <span className="font-sans text-[16px] font-extrabold leading-none tracking-[-0.01em]">
            RealscoreAI
          </span>
        </Link>

        <nav className="hidden items-center gap-5 text-[13.5px] font-semibold sm:flex">
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
        <nav className="flex flex-col border-t border-[var(--oasis-border)] px-4 py-2 text-[14px] font-semibold sm:hidden">
          {NAV_LINKS.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              onClick={() => setOpen(false)}
              className={cn(
                "border-b border-[var(--oasis-border-row)] py-[11px] last:border-0",
                link.match(pathname ?? "") ? "text-[var(--oasis-text)]" : "text-[var(--oasis-text-muted)]",
              )}
            >
              {link.label}
            </Link>
          ))}
          <Link href="/pricing" onClick={() => setOpen(false)} className="border-b border-[var(--oasis-border-row)] py-[11px] text-[var(--oasis-text-muted)]">
            Pricing
          </Link>
          <Show when="signed-out">
            <SignInButton mode="modal">
              <button type="button" className="py-[11px] text-left text-[var(--oasis-home)]">Sign in</button>
            </SignInButton>
          </Show>
          <span className="py-[8px] font-mono text-[11px] font-medium text-[var(--oasis-text-dim)]">data {utcClock(generatedAt)} UTC</span>
        </nav>
      )}
    </header>
  );
}
