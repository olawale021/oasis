import type { Metadata } from "next";
import { Instrument_Sans, JetBrains_Mono } from "next/font/google";
import { SiteHeader } from "@/components/site-header";
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
  title: "Oasis — Five-League Football Predictions",
  description:
    "Transparent, calibrated pre-match probabilities for the Premier League, La Liga, Serie A, Bundesliga and MLS. Probabilistic forecasts, not betting advice.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${instrumentSans.variable} ${jetBrainsMono.variable} h-full antialiased dark`}
    >
      <body className="flex min-h-full flex-col bg-[var(--oasis-bg)] text-[var(--oasis-text)]">
        <SiteHeader />
        <main className="flex-1">{children}</main>
      </body>
    </html>
  );
}
