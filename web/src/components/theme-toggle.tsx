"use client";

import { useSyncExternalStore } from "react";

type Theme = "dark" | "light";

function subscribe(cb: () => void) {
  const obs = new MutationObserver(cb);
  obs.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
  return () => obs.disconnect();
}
const getSnapshot = (): Theme => (document.documentElement.classList.contains("light") ? "light" : "dark");
const getServerSnapshot = (): Theme => "dark";

function apply(t: Theme) {
  const el = document.documentElement;
  el.classList.toggle("dark", t === "dark");
  el.classList.toggle("light", t === "light");
  try { localStorage.setItem("rs-theme", t); } catch {}
}

/** Dark is the brand default; the choice persists per browser. The theme
 * is read from the <html> class (set before first paint by the layout
 * script), so SSR renders dark and the client corrects itself without a
 * state update in an effect. */
export function ThemeToggle({ className = "" }: { className?: string }) {
  const theme = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
  const next: Theme = theme === "dark" ? "light" : "dark";
  return (
    <button
      type="button"
      aria-label={`Switch to ${next} mode`}
      title={`Switch to ${next} mode`}
      onClick={() => apply(next)}
      className={`rs-cta flex h-8 w-8 items-center justify-center rounded-[7px] border border-[var(--oasis-border-strong)] text-[var(--oasis-text-soft)] hover:text-[var(--oasis-text)] ${className}`}
    >
      {theme === "dark" ? (
        <svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><circle cx="8" cy="8" r="3" /><path d="M8 1.5v1.5M8 13v1.5M1.5 8H3M13 8h1.5M3.4 3.4l1 1M11.6 11.6l1 1M3.4 12.6l1-1M11.6 4.4l1-1" /></svg>
      ) : (
        <svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M13.5 9.5A6 6 0 0 1 6.5 2.5a6 6 0 1 0 7 7z" /></svg>
      )}
    </button>
  );
}
