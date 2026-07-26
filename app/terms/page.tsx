import type { Metadata } from "next";
import { PolicyPage, H2, P, UL } from "@/components/policy-page";

export const metadata: Metadata = {
  title: "Terms of Service — Saathi",
  description: "The terms on which Saathi is provided.",
};

export default function Terms() {
  return (
    <PolicyPage title="Terms of Service" updated="26 July 2026">
      <P>
        Saathi is a WhatsApp assistant for older adults, operated by Nuraveda Labs. By
        messaging Saathi you agree to these terms.
      </P>

      <H2>What Saathi does</H2>
      <P>
        Saathi remembers things you ask it to remember, sets reminders, answers questions,
        and helps make sense of confusing messages. It works in Hindi and English, by text
        or voice note.
      </P>

      <H2>What Saathi cannot do</H2>
      <P>
        Saathi cannot take any action on your behalf outside the chat. It cannot pay for
        anything, place an order, book a ticket, or sign in to any account. It has no such
        capability, by design.
      </P>

      <H2>Not medical, legal or financial advice</H2>
      <P>
        Saathi can remind you to take a medicine. It will not tell you which medicine to
        take, what dose, or whether to change one — only your doctor can. Nothing Saathi
        says is medical, legal or financial advice.
      </P>

      <H2>Not an emergency service</H2>
      <P>
        Saathi cannot call an ambulance, a doctor or a family member. In an emergency,
        call 112 or 108, or ask someone near you for help.
      </P>

      <H2>Accuracy</H2>
      <P>
        Saathi uses speech recognition and an AI model, and both can be wrong. It will read
        back times, dates, doses and names before acting on them — please check them. Do
        not rely on Saathi as your only reminder for anything critical.
      </P>

      <H2>Acceptable use</H2>
      <UL>
        <li>Use Saathi for yourself or for a family member who has agreed to it.</li>
        <li>Do not use it to harass anyone or to break the law.</li>
        <li>Do not attempt to make it act as a payment, medical or emergency service.</li>
      </UL>

      <H2>Stopping</H2>
      <P>
        You can stop at any time by saying so in the chat, and you can have everything
        deleted by saying &ldquo;forget everything about me&rdquo;. See{" "}
        <a className="underline" href="/data-deletion/">Delete your data</a>.
      </P>

      <H2>Contact</H2>
      <P>help.nuraveda@gmail.com</P>
    </PolicyPage>
  );
}
