import React from "react";

/**
 * The operating entity, stated once and reused, so the three policy pages can
 * never drift apart on who is legally responsible.
 *
 * Under India's DPDP Act the data fiduciary must be identifiable to the person
 * whose data it is — a policy that says only "we" is not compliant, and is not
 * much use to a family trying to work out who to write to.
 */
export const OPERATOR = {
  tradeName: "Bani Thani",
  legalName: "Harshita Goyal",
  constitution: "Proprietorship",
  gstin: "23AMMPG9088N1ZB",
  address:
    "GF-1, Gopal Tower, Shri Ram Colony, Gwalior, Madhya Pradesh 474002, India",
  email: "help.nuraveda@gmail.com",
};

export function OperatorBlock() {
  return (
    <div className="rounded-xl border border-gray-200 bg-gray-50 p-5 text-sm dark:border-gray-800 dark:bg-gray-800/40">
      <p className="font-medium text-gray-900 dark:text-white">
        {OPERATOR.tradeName} ({OPERATOR.constitution})
      </p>
      <p className="mt-1 text-gray-600 dark:text-gray-400">
        Proprietor: {OPERATOR.legalName}
        <br />
        {OPERATOR.address}
        <br />
        GSTIN: {OPERATOR.gstin}
        <br />
        Email: {OPERATOR.email}
      </p>
    </div>
  );
}
