import type { Metadata } from "next";
import { Instrument_Sans, JetBrains_Mono } from "next/font/google";
import { ClerkProvider } from "@clerk/nextjs";
import { shadcn } from "@clerk/ui/themes";
import { SiteHeader } from "@/components/site-header";
import { getLive } from "@/lib/live-server";
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
  title: "RealscoreAI — Five-League Football Forecasts",
  description:
    "Transparent, calibrated pre-match probabilities for the Premier League, La Liga, Serie A, Bundesliga and MLS. Probabilistic forecasts, not betting advice.",
};

export default async function RootLayout({ children }: LayoutProps<"/">) {
  const live = await getLive();
  return (
    <html
      lang="en"
      className={`${instrumentSans.variable} ${jetBrainsMono.variable} h-full antialiased dark`}
    >
      <body className="flex min-h-full flex-col bg-[var(--oasis-bg)] text-[var(--oasis-text)]">
        <ClerkProvider appearance={{ theme: shadcn }}>
          <SiteHeader generatedAt={live.generated_at} />
          <main className="flex-1">{children}</main>
        </ClerkProvider>
      </body>
    </html>
  );
}
