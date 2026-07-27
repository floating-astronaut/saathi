"""Asking to be paid — deterministically, and from nowhere the model can reach.

Saathi is an assistant for older adults, and the scam it exists to blunt is not
a stolen transfer: it is a trusted voice asking someone to pay for something.
So the product's promise has always been that it *never transacts*, enforced by
`assert_no_forbidden_tools()` rather than by intent.

The paywall does not change that promise, and this module is where the
difference lives:

* **No payment tool exists.** `order_details`, `send_invoice`, `request_payment`
  and friends are in `FORBIDDEN_TOOL_NAMES`; the suite fails if one is ever
  added to `TOOLS`. The model cannot send an invoice, cannot be persuaded to,
  and cannot be prompt-injected into it, because the capability is absent rather
  than guarded.
* **One caller, one price.** `capabilities._paywall_handle` calls this with
  `accounts.CONTINUE_PRICE_MINOR`. There is no path where an amount is chosen
  by anything that read user text.
* **Razorpay collects, not us.** They will not take a payment without a phone
  number or email, so the payer identity stays theirs. We keep only the join —
  `accounts.psp_customer_id` — so a captured payment lands on the right
  household. No card, no UPI handle, no contact detail we did not already have.

Disabled unless explicitly configured. An unconfigured install tells the user
their trial is over and sends no invoice, which is the right failure: a paywall
that half-works takes money without delivering, or promises without charging.
"""
from __future__ import annotations

import logging

from .config import settings

log = logging.getLogger("saathi.payments")


class PaymentsDisabled(RuntimeError):
    """Payments are not configured. Say nothing about money and move on.

    Raised rather than returning None so a caller cannot mistake "not
    configured" for "sent".
    """


def enabled() -> bool:
    return bool(settings.saathi_payments_enabled
                and settings.razorpay_merchant_id
                and settings.wa_payment_configuration_name)


def _assert_configured() -> None:
    if not settings.saathi_payments_enabled:
        raise PaymentsDisabled("SAATHI_PAYMENTS_ENABLED is off")
    if not settings.razorpay_merchant_id:
        raise PaymentsDisabled("RAZORPAY_MERCHANT_ID is not set")
    if not settings.wa_payment_configuration_name:
        raise PaymentsDisabled("WA_PAYMENT_CONFIGURATION_NAME is not set")


def build_order_details(*, reference: str, amount_minor: int,
                        description: str) -> dict:
    """The `order_details` payload WhatsApp expects, in paise.

    Split out from sending so the shape can be asserted in a test without any
    network, and so the amount arithmetic has exactly one home. Amounts are
    integer minor units throughout — a float rupee is how you end up a paisa out
    on the one invoice somebody disputes.
    """
    if amount_minor <= 0:
        raise ValueError("an invoice must be for a positive amount")
    return {
        "type": "interactive",
        "interactive": {
            "type": "order_details",
            "body": {"text": description},
            "action": {
                "name": "review_and_pay",
                "parameters": {
                    "reference_id": reference,
                    "type": "digital-goods",
                    "payment_configuration": settings.wa_payment_configuration_name,
                    "currency": "INR",
                    "total_amount": {"value": amount_minor, "offset": 100},
                    "order": {
                        "status": "pending",
                        "items": [{
                            "name": description,
                            "amount": {"value": amount_minor, "offset": 100},
                            "quantity": 1,
                        }],
                        "subtotal": {"value": amount_minor, "offset": 100},
                    },
                },
            },
        },
    }


async def send_invoice(conn, transport, user_id: int, handle: str, *,
                       amount_minor: int,
                       description: str = "Saathi — aage jaari rakhein") -> str:
    """Send one invoice for a fixed amount. Raises if payments are not configured.

    Records the intent in `account_payments` **before** sending, so an invoice
    that reaches the user and a webhook we then fail to process still has a row
    to reconcile against. The reference is ours and unique, which is what stops
    a replayed webhook crediting the same payment twice.
    """
    _assert_configured()

    row = await (await conn.execute(
        "select account_id from users where id = %s", (user_id,))).fetchone()
    if not row or not row[0]:
        raise PaymentsDisabled(f"user {user_id} has no account to bill")
    account_id = row[0]

    reference = f"saathi:{settings.saathi_env}:acct{account_id}:{amount_minor}"
    await conn.execute(
        """insert into account_payments (account_id, amount_minor, reference)
           values (%s, %s, %s)
           on conflict (reference) do nothing""",
        (account_id, amount_minor, reference))

    if not transport.capabilities.supports_payments:
        raise PaymentsDisabled(f"{transport.channel} cannot carry an invoice")

    payload = build_order_details(reference=reference, amount_minor=amount_minor,
                                  description=description)
    mid = await transport.send_order_details(conn, user_id, handle, payload)
    # Amount and account. Never the payer's contact details — those are
    # Razorpay's to hold, and the reason this integration is worth having.
    log.info("invoice sent to account %s for %s paise", account_id, amount_minor)
    return mid
