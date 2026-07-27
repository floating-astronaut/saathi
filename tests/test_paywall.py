"""The paywall: what it takes away, and — more importantly — what it must not.

Saathi's promise to an older adult is that it never asks them for money. The
paywall changes that, and this file is where the change is bounded.

Two properties matter more than the billing:

1. **The model can never send an invoice.** `order_details` and friends are in
   `FORBIDDEN_TOOL_NAMES`, so a forwarded scam cannot talk the agent into
   billing someone — the capability is absent, not guarded.
2. **An unpaid account keeps its rights.** Safety, onboarding, erasing your
   data, acknowledging a reminder, and STOP all sit *below* the paywall in the
   chain and keep working. Reminders keep firing because they run from the
   worker and never enter this chain at all. An unpaid bill is not a reason to
   stop telling someone to take their heart medication.
"""
import pytest

from saathi import accounts, capabilities, payments
from saathi.agent.tools.specs import (FORBIDDEN_TOOL_NAMES, TOOLS,
                                      assert_no_forbidden_tools)
from saathi.config import settings
from saathi.core.handlers import registered


class Cur:
    def __init__(self, rows=None): self._rows = rows or []
    async def fetchone(self): return self._rows[0] if self._rows else None
    async def fetchall(self): return self._rows


class Conn:
    def __init__(self, rows=None):
        self.sql, self.rows = [], rows or {}

    async def execute(self, q, params=None):
        flat = " ".join(q.split())
        self.sql.append(flat)
        for needle, r in self.rows.items():
            if needle in flat:
                return Cur(r)
        return Cur()


class Caps:
    def __init__(self, pay=True): self.supports_payments = pay


class Transport:
    channel = "whatsapp"

    def __init__(self, pay=True):
        self.capabilities = Caps(pay)
        self.sent = []

    async def send_order_details(self, conn, user_id, handle, payload):
        self.sent.append(payload)
        return "wamid.INVOICE"


class Ctx:
    def __init__(self, status="exhausted", lang="hi", pay=True):
        self.account_status = status
        self.user_id = 1
        self.handle = "919999999999"
        self.conn = Conn({"lang_pref": [(lang,)], "account_id from users": [(7,)]})
        self.transport = Transport(pay)
        self.replies = []

    async def reply(self, text):
        self.replies.append(text)


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setattr(settings, "saathi_payments_enabled", True, raising=False)
    monkeypatch.setattr(settings, "razorpay_merchant_id", "acc_TEST", raising=False)
    monkeypatch.setattr(settings, "wa_payment_configuration_name", "indofolk",
                        raising=False)


# --- the capability the model must never have -------------------------------

def test_no_invoice_tool_is_exposed_to_the_model():
    """A forwarded scam cannot argue with a tool that does not exist."""
    assert_no_forbidden_tools()
    names = {t["toolSpec"]["name"] for t in TOOLS}
    assert not (names & {"send_invoice", "request_payment", "order_details",
                         "charge", "refund"})


def test_the_invoice_names_are_forbidden_by_the_guard():
    # Guards the guard: if someone drops these from the set, the test above
    # would still pass while meaning nothing.
    for name in ("send_invoice", "request_payment", "order_details", "charge"):
        assert name in FORBIDDEN_TOOL_NAMES


# --- what an unpaid account keeps -------------------------------------------

def test_the_paywall_sits_above_every_deterministic_capability():
    """Rights are not features to be sold back to someone.

    Safety, onboarding, erasing your data, acking a reminder, and STOP must all
    resolve before the paywall is ever consulted.
    """
    order = {h.name: h.priority for h in registered()}
    for kept in ("safety", "onboarding", "erase_confirm", "reminder_ack", "commands"):
        assert order[kept] < order["paywall"], f"{kept} is gated by the paywall"


def test_the_paywall_gates_only_the_model_turn():
    order = {h.name: h.priority for h in registered()}
    assert order["paywall"] < order["agent"]


def test_an_active_account_is_not_paywalled():
    assert not capabilities._paywall_matches(Ctx(status="active"))


def test_a_paid_account_is_not_paywalled():
    assert not capabilities._paywall_matches(Ctx(status="paid"))


def test_an_exhausted_account_is():
    assert capabilities._paywall_matches(Ctx(status="exhausted"))


def test_the_matcher_is_synchronous():
    """The trap this design avoids.

    `dispatch` calls `if not h.matches(ctx)`. An async matcher returns a
    coroutine, which is truthy — so it would match *every* message and put the
    entire user base behind the paywall, silently.
    """
    import inspect
    assert not inspect.iscoroutinefunction(capabilities._paywall_matches)


def test_a_missing_account_row_does_not_lock_someone_out():
    """Fail open, not closed — this one time.

    Everywhere else in this codebase an unknown value takes the safe-for-us
    branch. Here the safe branch is the user's: a half-run migration must not
    look like an unpaid bill to somebody who trusts this thing.
    """
    import asyncio
    conn = Conn({})           # no account row at all
    assert asyncio.run(accounts.status_of(conn, user_id=1)) == "active"


# --- the reply --------------------------------------------------------------

async def test_the_user_is_told_in_their_own_language():
    hi, en = Ctx(lang="hi", pay=False), Ctx(lang="en", pay=False)
    await capabilities._paywall_handle(hi)
    await capabilities._paywall_handle(en)
    assert hi.replies[0] == capabilities.PAYWALL_COPY["hi"]
    assert en.replies[0] == capabilities.PAYWALL_COPY["en"]


async def test_the_reply_promises_that_reminders_continue():
    """Because they do, and it is the thing a person would most fear losing."""
    for copy in capabilities.PAYWALL_COPY.values():
        assert "reminder" in copy.lower()


async def test_an_unconfigured_install_says_so_but_sends_no_invoice():
    ctx = Ctx()                       # payments not enabled
    out = await capabilities._paywall_handle(ctx)
    assert out["handled"] == "paywall"
    assert ctx.replies, "the user was told nothing"
    assert not ctx.transport.sent, "an invoice went out on an unconfigured install"


async def test_the_kill_switch_alone_stops_the_invoice(monkeypatch):
    """Pinned on its own, because the obvious test passes for the wrong reason.

    With the gateway fully configured and only `saathi_payments_enabled` off,
    nothing may go out. An earlier version of this file asserted "unconfigured
    sends nothing" while *also* leaving the merchant id blank — so it stayed
    green when the flag was deleted from the code entirely.
    """
    monkeypatch.setattr(settings, "saathi_payments_enabled", False, raising=False)
    monkeypatch.setattr(settings, "razorpay_merchant_id", "acc_TEST", raising=False)
    monkeypatch.setattr(settings, "wa_payment_configuration_name", "indofolk",
                        raising=False)
    ctx = Ctx()
    await capabilities._paywall_handle(ctx)
    assert not ctx.transport.sent, "the kill switch did not stop the invoice"


async def test_a_configured_install_sends_exactly_one_invoice(configured):
    ctx = Ctx()
    await capabilities._paywall_handle(ctx)
    assert len(ctx.transport.sent) == 1


# --- the money ---------------------------------------------------------------

def test_the_amount_is_integer_paise(configured):
    body = payments.build_order_details(reference="r", amount_minor=19900,
                                        description="d")
    total = body["interactive"]["action"]["parameters"]["total_amount"]
    assert total == {"value": 19900, "offset": 100}
    assert isinstance(total["value"], int), "money must never be a float"


def test_the_price_comes_from_one_constant_not_from_user_text():
    assert accounts.CONTINUE_PRICE_MINOR == 19900


def test_an_invoice_for_nothing_is_refused(configured):
    for bad in (0, -1):
        with pytest.raises(ValueError):
            payments.build_order_details(reference="r", amount_minor=bad,
                                         description="d")


async def test_a_channel_without_payments_refuses_rather_than_failing_quietly(
        configured):
    ctx = Ctx(pay=False)
    ctx.transport.channel = "telegram"
    with pytest.raises(payments.PaymentsDisabled):
        await payments.send_invoice(ctx.conn, ctx.transport, 1, "h",
                                    amount_minor=19900)
