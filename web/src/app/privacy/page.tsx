import type { Metadata } from "next";
import { Fill, LegalPage, Section } from "@/components/legal/legal-page";

export const metadata: Metadata = { title: "RealscoresAI — Privacy policy", description: "What RealscoresAI collects, why, and how to control it." };

export default function PrivacyPage() {
  return (
    <LegalPage
      title="Privacy policy"
      updated="17 September 2026"
      intro="RealscoresAI publishes football forecasts. We collect as little personal data as the service needs, we do not sell it, and this page says exactly what we keep and why."
    >
      <Section title="1 · Who we are">
        <p>
          RealscoresAI is operated by <Fill what="legal entity name" />, <Fill what="registered address" />. Questions about this policy go to{" "}
          <Fill what="privacy contact email" />.
        </p>
      </Section>
      <Section title="2 · What we collect">
        <ul>
          <li><strong>Account data.</strong> When you sign in with Google or an email code we receive your email address, name and, from Google, your profile picture. Sign-in is handled by Clerk, our authentication provider, which stores this on our behalf.</li>
          <li><strong>Access status.</strong> Whether your account has lifetime access, and the date it was granted.</li>
          <li><strong>Payment records.</strong> If you buy lifetime access, the payment is processed by Stripe. We receive a payment reference, the amount and your email. We never see or store card numbers.</li>
          <li><strong>Preferences.</strong> Your theme choice is stored in your browser only. Alert preferences and a Telegram link, once those features exist, are stored with your account.</li>
          <li><strong>Betting section.</strong> We do not know whether you bet, with whom, or how much. The site takes no bets, has no connection to any bookmaker account, and does not track what you do after leaving it. Grades, edges and the performance record are computed from match and odds data, not from anything about you. We rely on your confirmation that you are over 18; we do not run identity or age-verification checks.</li>
          <li><strong>Technical logs.</strong> Our host, Cloudflare, records request logs, including IP address and browser type, for security and to keep the service running. We do not use advertising trackers or third-party analytics.</li>
        </ul>
      </Section>
      <Section title="3 · Why we use it">
        <ul>
          <li>To sign you in and show you the access you have paid for.</li>
          <li>To send emails you have asked for: sign-in codes, purchase receipts and, if you opt in, alerts.</li>
          <li>To keep the service secure and to investigate abuse.</li>
          <li>To meet legal obligations such as tax and accounting records.</li>
        </ul>
        <p>The legal bases, where the UK or EU rules apply, are performance of our contract with you, our legitimate interest in running a secure service, and consent for optional alerts.</p>
      </Section>
      <Section title="4 · Cookies">
        <p>
          We set only the cookies needed to keep you signed in, provided by Clerk, and Cloudflare&apos;s security cookies. There are no advertising or cross-site tracking cookies. Blocking cookies will sign you out.
        </p>
      </Section>
      <Section title="5 · Who we share it with">
        <ul>
          <li><strong>Clerk</strong> for authentication.</li>
          <li><strong>Stripe</strong> for payments.</li>
          <li><strong>Cloudflare</strong> for hosting and delivery.</li>
          <li><strong>Telegram</strong>, only if you connect a Telegram account for alerts.</li>
        </ul>
        <p>Each of these processes data under its own agreement with us and its own privacy policy. We do not sell personal data and we do not share it with advertisers.</p>
      </Section>
      <Section title="6 · How long we keep it">
        <p>
          Account data is kept while your account exists. Payment records are kept for <Fill what="retention period, e.g. 7 years" /> to meet accounting rules. Request logs are kept by Cloudflare for a short rolling period. Forecast data on the site is not personal data and is kept permanently as the public record.
        </p>
      </Section>
      <Section title="7 · Your rights">
        <p>
          You can ask for a copy of your data, ask us to correct it, or ask us to delete your account. Deleting your account removes your login and preferences; payment records we are required to keep by law are retained. Email <Fill what="privacy contact email" /> and we will respond within 30 days. You may also complain to your local data protection authority.
        </p>
      </Section>
      <Section title="8 · Children">
        <p>The service, and the Betting section in particular, is for adults. We do not knowingly collect data from anyone under 18, and accounts found to belong to minors are closed.</p>
      </Section>
      <Section title="9 · Changes">
        <p>If this policy changes in a way that matters, we will say so on the site and update the date at the top of this page.</p>
      </Section>
    </LegalPage>
  );
}
