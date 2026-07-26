import type { Metadata } from "next";
import { PolicyPage, H2, P, UL } from "@/components/policy-page";

export const metadata: Metadata = {
  title: "Privacy Policy — Saathi",
  description:
    "What Saathi stores, where it is stored, how long it is kept, and how to have it deleted.",
};

export default function Privacy() {
  return (
    <PolicyPage title="Privacy Policy" updated="26 July 2026">
      <P>
        Saathi is a WhatsApp assistant for older adults, operated by Nuraveda Labs. This
        policy describes exactly what we store, where, for how long, and how to have it
        removed. It is written to be read by the person using Saathi, not only by lawyers.
      </P>

      <H2>What we store</H2>
      <UL>
        <li>Your WhatsApp number and the display name WhatsApp provides.</li>
        <li>The messages you send us and the replies we send you.</li>
        <li>
          For voice notes: a transcript of what you said. The audio recording itself is
          deleted after 7 days; only the transcript is kept.
        </li>
        <li>
          Facts you explicitly ask us to remember — a medicine, a doctor, a family member,
          a routine. We do not infer these silently; each one comes from something you told
          us to remember, and you can see the full list at any time.
        </li>
        <li>Reminders you create, and whether they were acknowledged.</li>
      </UL>

      <H2>What we never do</H2>
      <UL>
        <li>
          <strong>We never take payments or place orders.</strong> Saathi has no ability to
          spend money. This is not a policy promise — the software simply has no such
          function.
        </li>
        <li>
          <strong>We never ask for an OTP, PIN or password.</strong> If anyone asks you for
          one while claiming to be us, it is a scam.
        </li>
        <li><strong>We never access your bank, email or other accounts.</strong></li>
        <li><strong>We never sell or rent your data.</strong></li>
        <li>We do not give medical, legal or financial advice.</li>
      </UL>

      <H2>Where your data is stored</H2>
      <P>
        Your data is stored in India (Mumbai, AWS ap-south-1). Speech recognition is
        performed by Sarvam AI, an Indian provider. The AI model that composes replies runs
        on Amazon Bedrock in the Mumbai region.
      </P>
      <P>
        One honest exception: some AI models are served by Amazon across multiple regions
        rather than only India, and where that applies your message text may be processed
        outside India during the reply. Your stored data — messages, transcripts,
        reminders and remembered facts — stays in India.
      </P>

      <H2>How long we keep it</H2>
      <UL>
        <li><strong>Voice recordings:</strong> 7 days, then deleted automatically.</li>
        <li><strong>Transcripts and messages:</strong> until you delete them or your account.</li>
        <li><strong>Remembered facts and reminders:</strong> until you delete them.</li>
      </UL>

      <H2>Your rights</H2>
      <P>
        Under India&rsquo;s Digital Personal Data Protection Act, you may access, correct
        and erase your personal data, and withdraw consent. In Saathi you can do all of it
        by asking, in your own words, in the chat:
      </P>
      <UL>
        <li>&ldquo;What do you know about me?&rdquo; — see everything stored.</li>
        <li>&ldquo;Forget that&rdquo; — remove one fact.</li>
        <li>&ldquo;Delete that message&rdquo; — remove a message.</li>
        <li>
          &ldquo;Forget everything about me&rdquo; — erase everything. This is a real
          deletion, not a hidden flag.
        </li>
      </UL>

      <H2>Improving the service</H2>
      <P>
        Saathi can learn to understand Indian speech better over time — for example, that a
        particular medicine name is often misheard. This is <strong>optional and off by
        default</strong>, and asked separately from the consent needed to use the service.
      </P>
      <P>If you do opt in, what we keep is deliberately narrow:</P>
      <UL>
        <li>
          Only word pairs — how a word was misheard and what it should have been — never
          your conversations.
        </li>
        <li>
          <strong>Never names of people or places.</strong> Only shared vocabulary such as
          medicine and brand names.
        </li>
        <li>
          A word pair is used only once at least five different people have produced it, so
          nothing unique to you is ever included.
        </li>
        <li>If you withdraw consent, everything you contributed is deleted.</li>
      </UL>

      <H2>Emergencies</H2>
      <P>
        Saathi is not an emergency service and cannot call anyone for you. If you describe
        what looks like a medical emergency, it will show you emergency numbers (112, 108)
        and urge you to call someone. Always call a person.
      </P>

      <H2>Contact</H2>
      <P>
        Questions, complaints, or a data request you would rather not make in the chat:
        write to <strong>help.nuraveda@gmail.com</strong>. We respond to data requests
        within 30 days.
      </P>
    </PolicyPage>
  );
}
