import type { Metadata } from "next";
import { PolicyPage, H2, P, UL } from "@/components/policy-page";

export const metadata: Metadata = {
  title: "Delete your data — Saathi",
  description: "How to have everything Saathi stores about you permanently deleted.",
};

export default function DataDeletion() {
  return (
    <PolicyPage title="Delete your data" updated="26 July 2026">
      <P>
        You can have everything Saathi stores about you permanently deleted. There are two
        ways, and both result in real deletion — not a hidden flag or an archived copy.
      </P>

      <H2>1. Ask in the chat (fastest)</H2>
      <P>Send Saathi a message on WhatsApp saying, in Hindi or English:</P>
      <UL>
        <li>&ldquo;Forget everything about me&rdquo;</li>
        <li>&ldquo;Mere baare mein sab kuch bhool jao&rdquo;</li>
      </UL>
      <P>
        Saathi will confirm once before deleting, because it cannot be undone. After you
        confirm, your remembered facts, messages, transcripts, reminders and any voice
        recordings are deleted immediately.
      </P>
      <P>To delete only part of it:</P>
      <UL>
        <li>&ldquo;Forget that&rdquo; — removes a single remembered fact.</li>
        <li>&ldquo;Delete that message&rdquo; — removes a message.</li>
        <li>&ldquo;Clear this chat&rdquo; — removes the conversation but keeps your reminders.</li>
      </UL>

      <H2>2. Email us</H2>
      <P>
        Write to <strong>help.nuraveda@gmail.com</strong> from any address, telling us the
        WhatsApp number to delete. We will confirm the request on that WhatsApp number
        before acting — this protects you from someone else deleting your data — and
        complete it within 30 days, usually much sooner.
      </P>

      <H2>What gets deleted</H2>
      <UL>
        <li>Everything you asked Saathi to remember.</li>
        <li>Your messages, replies and voice transcripts.</li>
        <li>Any voice recordings still within their 7-day window.</li>
        <li>Your reminders.</li>
        <li>Anything you contributed to service improvement, if you had opted in.</li>
      </UL>

      <H2>What we keep, and why</H2>
      <P>
        We keep a minimal record that a deletion request was made and completed. It
        contains no personal content and exists so we can demonstrate the request was
        honoured.
      </P>

      <H2>Contact</H2>
      <P>help.nuraveda@gmail.com</P>
    </PolicyPage>
  );
}
