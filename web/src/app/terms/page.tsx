import type { Metadata } from "next";
import { Fill, LegalPage, Section } from "@/components/legal/legal-page";

export const metadata: Metadata = { title: "RealscoresAI — Terms and conditions", description: "The terms for using RealscoresAI and buying lifetime access." };

export default function TermsPage() {
  return (
    <LegalPage
      title="Terms and conditions"
      updated="13 September 2026"
      intro="These terms cover using the RealscoresAI website and buying lifetime access. Using the site means you accept them. Please read the part about forecasts carefully: they are probabilities, not promises."
    >
      <Section title="1 · The service">
        <p>
          RealscoresAI, operated by <Fill what="legal entity name" />, publishes pre-match probability forecasts for football matches in the Premier League, La Liga, Serie A, Bundesliga and MLS, together with a public record of how those forecasts performed. Some content is free; some requires lifetime access.
        </p>
      </Section>
      <Section title="2 · Forecasts are not advice">
        <ul>
          <li>Every number on the site is a probability estimate produced by a statistical model. A 70% forecast is expected to be wrong roughly three times in ten.</li>
          <li>Nothing on the site is betting, financial or investment advice, and nothing is a recommendation to place a bet. If you choose to bet, you do so entirely at your own risk and in line with the law where you live.</li>
          <li>Bookmaker odds shown for comparison come from third parties and may be delayed or differ from what any bookmaker offers you.</li>
          <li>We publish past performance honestly, including misses, but past performance does not predict future results.</li>
        </ul>
      </Section>
      <Section title="3 · Who may use the site">
        <p>You must be at least 18 years old, or the legal age for gambling-related content where you live if that is higher. You are responsible for making sure using the site is lawful where you are.</p>
      </Section>
      <Section title="4 · Accounts">
        <ul>
          <li>You need an account for the free daily forecasts and for lifetime access. Keep your sign-in secure; you are responsible for activity on your account.</li>
          <li>One person per account. Sharing an account, or reselling or scraping site content, is not permitted and may lead to the account being closed without refund.</li>
        </ul>
      </Section>
      <Section title="5 · Lifetime access">
        <ul>
          <li>Lifetime access is a one-time purchase that unlocks every upcoming forecast and the related features for as long as RealscoresAI operates the service. &ldquo;Lifetime&rdquo; means the lifetime of the product, not of the purchaser.</li>
          <li>The founding-member offer is limited in number and price, and may be withdrawn once the cap is reached.</li>
          <li>Access covers the leagues and features listed at the time of purchase. We may add leagues and features; we will not remove core features you paid for without offering a remedy.</li>
          <li>If we permanently shut the service down, access ends. We will give at least <Fill what="notice period, e.g. 90 days" /> notice where we can.</li>
        </ul>
      </Section>
      <Section title="6 · Payments and refunds">
        <ul>
          <li>Payments are taken by Stripe. Prices are shown in <Fill what="currency" /> and include any applicable tax unless stated otherwise.</li>
          <li>Because lifetime access is digital content delivered immediately, you agree that supply starts at once. Where consumer law gives you a cancellation right, you can cancel within 14 days of purchase for a full refund provided you have not used premium features; otherwise the refund may be reduced or refused as the law allows.</li>
          <li>Refund requests go to <Fill what="support contact email" />. We aim to answer within five working days.</li>
        </ul>
      </Section>
      <Section title="7 · Availability and changes">
        <p>
          We work to keep the site available and forecasts published before kickoff, but we do not guarantee uninterrupted service, that every match will have a forecast, or that data from our providers will be complete. We may change the models, the site and these terms; material changes to the terms will be announced on the site with a new date at the top of this page.
        </p>
      </Section>
      <Section title="8 · Intellectual property and data">
        <p>
          The forecasts, text, design and code of the site belong to us. Match data, odds and club crests belong to their respective owners and are used under licence or as permitted. You may quote individual forecasts with attribution; you may not republish the site&apos;s data in bulk or use it to train or operate a competing service.
        </p>
      </Section>
      <Section title="9 · Liability">
        <p>
          To the fullest extent the law allows, we are not liable for any loss arising from reliance on a forecast, including any betting loss, or for indirect or consequential loss. Our total liability to you for anything else is limited to the amount you paid us. Nothing in these terms limits liability that cannot be limited by law.
        </p>
      </Section>
      <Section title="10 · Responsible use">
        <p>
          If gambling is causing you or someone close to you harm, help is available. In the UK, GamCare offers free support on 0808 8020 133. Please use the forecasts as information, not as a system.
        </p>
      </Section>
      <Section title="11 · Governing law and contact">
        <p>
          These terms are governed by the law of <Fill what="jurisdiction, e.g. England and Wales" /> and disputes go to its courts, without affecting consumer rights you have where you live. Contact: <Fill what="support contact email" />.
        </p>
      </Section>
    </LegalPage>
  );
}
