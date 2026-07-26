import React from "react";

/**
 * The operating entity, stated once and reused, so the three policy pages can
 * never drift apart on who is legally responsible.
 *
 * These details deliberately mirror the business verified in Meta Business
 * Manager (`ayurpetofficial`, which owns the WhatsApp Business Account). A
 * reviewer cross-checks the entity named in the privacy policy against the
 * verified business, and a mismatch reads as impersonation.
 *
 * Under India's DPDP Act the data fiduciary must be identifiable to the person
 * whose data it is — a policy that says only "we" is neither compliant nor much
 * use to a family trying to work out who to write to.
 */
export const OPERATOR = {
  legalName: "Indofolk Wellness Private Limited",
  constitution: "Private Limited Company",
  address: "S-258 S Block, Greater Kailash I, New Delhi, Delhi 110048, India",
  phone: "+91 99773 13509",
  website: "https://indofolkwellness.com/",
  gstin: "07AAHCI7432A1ZV",
  email: "help.nuraveda@gmail.com",
};

export function OperatorBlock() {
  return (
    <div className="rounded-xl border border-gray-200 bg-gray-50 p-5 text-sm dark:border-gray-800 dark:bg-gray-800/40">
      <p className="font-medium text-gray-900 dark:text-white">{OPERATOR.legalName}</p>
      <p className="mt-1 text-gray-600 dark:text-gray-400">
        {OPERATOR.constitution}
        <br />
        {OPERATOR.address}
        <br />
        GSTIN: {OPERATOR.gstin}
        <br />
        Phone: {OPERATOR.phone}
        <br />
        Email: {OPERATOR.email}
        <br />
        Web:{" "}
        <a className="underline" href={OPERATOR.website}>
          indofolkwellness.com
        </a>
      </p>
    </div>
  );
}
