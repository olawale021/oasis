"use client";

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
            <span className="h-[6px] w-[6px] rounded-full bg-[var(--oasis-positive)]" />
            data {utcClock(generatedAt)} UTC
          </span>
          <Link
            href="/pricing"
            className="rs-cta whitespace-nowrap rounded-[7px] bg-[var(--oasis-home)] px-[11px] py-[6px] text-[11.5px] font-bold text-[var(--oasis-home-ink)] sm:px-[13px] sm:py-[7px] sm:text-[12.5px]"
          >
            Get lifetime access
          </Link>
          <Show when="signed-out">
            <SignInButton mode="modal">
              <button
                type="button"
                className="rs-cta whitespace-nowrap rounded-[7px] border border-[var(--oasis-border-strong)] px-[11px] py-[6px] text-[11.5px] font-semibold text-[var(--oasis-text-soft)] hover:text-[var(--oasis-text)] sm:px-[13px] sm:py-[7px] sm:text-[12.5px]"
              >
                Sign in
              </button>
            </SignInButton>
          </Show>
          <Show when="signed-in">
            <UserButton />
          </Show>
        </div>
      </div>

      <nav className="flex items-center gap-5 overflow-x-auto px-4 pb-[10px] text-[12.5px] font-semibold sm:hidden">
        {NAV_LINKS.map((link) => (
          <Link
            key={link.href}
            href={link.href}
            className={cn(
              "whitespace-nowrap transition-colors",
              link.match(pathname ?? "")
                ? "text-[var(--oasis-text)]"
                : "text-[var(--oasis-text-muted)]",
            )}
          >
            {link.label}
          </Link>
        ))}
        <span className="cursor-default whitespace-nowrap text-[var(--oasis-text-muted)]">Pricing</span>
      </nav>
    </header>
  );
}
