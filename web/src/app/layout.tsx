import type { Metadata } from "next";
import { Instrument_Sans, JetBrains_Mono } from "next/font/google";
import { ClerkProvider } from "@clerk/nextjs";
import { shadcn } from "@clerk/ui/themes";
import { SiteHeader } from "@/components/site-header";
import { getLive } from "@/lib/live-server";
import { getViewer } from "@/lib/viewer";
import "./globals.css";

const instrumentSans = Instrument_Sans({
  variable: "--font-sans",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
});

const jetBrainsMono = JetBrains_Mono({
  variable: "--font-mono",
  subsets: ["latin"],
  weight: ["400", "500", "700"],
});

export const metadata: Metadata = {
  title: "RealscoresAI — Five-League Football Forecasts",
  description:
    "Transparent, calibrated pre-match probabilities for the Premier League, La Liga, Serie A, Bundesliga and MLS. Probabilistic forecasts, not betting advice.",
};

export default async function RootLayout({ children }: LayoutProps<"/">) {
  const [live, viewer] = await Promise.all([getLive(), getViewer()]);
  return (
    <html
      lang="en"
      suppressHydrationWarning
      className={`${instrumentSans.variable} ${jetBrainsMono.variable} h-full antialiased dark`}
    >
      <head>
        {/* Theme before first paint: stored choice wins, else dark (brand default). */}
        <script
          dangerouslySetInnerHTML={{
            __html: `(function(){try{var t=localStorage.getItem("rs-theme");if(t==="light"){document.documentElement.classList.remove("dark");document.documentElement.classList.add("light");}}catch(e){}})();`,
          }}
        />
      </head>
      {/* App shell: the header stays put and <main> is the scroller, so a
          page can fill the viewport (the home console) or flow past it
          (method, performance) without the window itself growing. */}
      <body className="flex h-dvh flex-col overflow-hidden bg-[var(--oasis-bg)] text-[var(--oasis-text)]">
        <ClerkProvider appearance={{ theme: shadcn }}>
          <SiteHeader generatedAt={live.generated_at} tier={viewer.tier} />
          <main className="min-h-0 flex-1 overflow-y-auto">{children}</main>
        </ClerkProvider>
      </body>
    </html>
  );
}
