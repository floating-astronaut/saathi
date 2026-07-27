"""The account tenant.

A phone number is a **revocable handle**, not a tenant. India recycles numbers
after roughly ninety days, which is why dormant handles re-verify at sixty — so
anything durable (spend, a minted vendor key, a bill) must hang off an account
that survives the number changing hands. `docs/AI_ROUTING.md` §4.

For beta each tester is their own account. The shape is right anyway, because
an account id given to a vendor is not one that can be quietly redefined later.
"""
from __future__ import annotations

import logging
from decimal import Decimal

log = logging.getLogger("saathi.accounts")

#: Monthly spend ceiling per tier, in USD.
#:
#: `free` is **not** a small cap — it is no key at all. A free account runs on
#: the platform default (Bedrock direct, as today), so admission staying open
#: does not hand a stranger a budget. That matters: onboarding is deliberately
#: open and model-free, and it would stop being safe if merely arriving minted
#: something billable.
#:
#: `paid` is provisional — nobody pays yet, and the number should be set by a
#: real price, not by symmetry with beta.
TIER_CAPS: dict[str, Decimal | None] = {
    "free": None,
    "beta": Decimal("5.00"),
    "paid": Decimal("20.00"),
}

#: New accounts start here. Not `beta`: the door is open by design, so the
#: default must be the tier that costs nothing to hand to a stranger. An
#: operator promotes a tester deliberately.
DEFAULT_TIER = "free"


def tier_cap(tier: str | None) -> Decimal | None:
    """Cap for a tier. An unknown tier gets the **lowest**, never the highest.

    Fail safe, not open — the same shape as `assert_no_forbidden_tools()`. A
    typo in a tier name, or a tier added to the enum and forgotten here, must
    cost nothing rather than everything.
    """
    if tier not in TIER_CAPS:
        log.warning("unknown tier %r — falling back to %r", tier, DEFAULT_TIER)
        return TIER_CAPS[DEFAULT_TIER]
    return TIER_CAPS[tier]


async def ensure_for_user(conn, user_id: int, tier: str = DEFAULT_TIER) -> int:
    """Return this user's account id, creating one if they have none.

    Idempotent by the `account_id is null` guard, the same shape migration 008
    uses for its backfill — 003 and 005 are why every backfill in this codebase
    is written to survive running twice.

    Concurrency: two callers racing on a brand-new user can both insert an
    `accounts` row; the `update ... where account_id is null` decides which one
    wins, and the re-read below returns the winner's id to both. The loser
    leaves an unreferenced account row. That is untidy rather than harmful, and
    stated plainly because a comment claiming race-freedom would be false.
    """
    row = await (await conn.execute(
        "select account_id from users where id = %s", (user_id,))).fetchone()
    if row and row[0]:
        return row[0]

    account_id = (await (await conn.execute(
        "insert into accounts (tier, label) values (%s, %s) returning id",
        (tier, f"user {user_id}"))).fetchone())[0]
    await conn.execute(
        "update users set account_id = %s where id = %s and account_id is null",
        (account_id, user_id))

    row = await (await conn.execute(
        "select account_id from users where id = %s", (user_id,))).fetchone()
    settled = row[0] if row and row[0] else account_id
    log.info("account %s for user %s (tier %s)", settled, user_id, tier)
    return settled


async def tier_of(conn, account_id: int) -> str:
    """The account's tier, or the default if the row has vanished."""
    row = await (await conn.execute(
        "select tier::text from accounts where id = %s and deleted_at is null",
        (account_id,))).fetchone()
    return row[0] if row else DEFAULT_TIER
