"""Put a beta tester on their own capped key.

    uv run python -m saathi.admin.grant --wa-id 919876543210 --tier beta
    uv run python -m saathi.admin.grant --wa-id 919876543210 --show
    uv run python -m saathi.admin.grant --wa-id 919876543210 --revoke

This is the whole operator workflow for handing someone a tester account. It
does two things and refuses to do a third:

* promotes the tester's account to a tier that has a cap, and
* **enqueues** the mint rather than performing it, because provisioning belongs
  on `scheduled_turns` (`AI_ROUTING.md` §7) — the worker owns retries, the
  audit trail and the idempotency, and this command should not grow a second
  copy of any of that.

It never prints key material. There is nothing to print: the plaintext is
encrypted inside the worker and the row stores ciphertext. If you need the key
itself, it is in the OpenRouter dashboard under the name shown by `--show`.
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone

from .. import accounts, db, openrouter, scheduling
from ..worker import turns  # noqa: F401 — registers `provision_key`


async def _user_by_wa_id(conn, wa_id: str):
    return await (await conn.execute(
        """select u.id, u.account_id, u.display_name, a.tier::text
             from users u left join accounts a on a.id = u.account_id
            where u.wa_id = %s and u.deleted_at is null""", (wa_id,))).fetchone()


async def _show(conn, wa_id: str) -> int:
    row = await _user_by_wa_id(conn, wa_id)
    if not row:
        print(f"no user with wa_id {wa_id}")
        return 1
    user_id, account_id, name, tier = row
    print(f"user {user_id} ({name or 'unnamed'})  account {account_id}  tier {tier}")
    if not account_id:
        return 0
    key = await openrouter.active_key_row(conn, account_id)
    if key:
        # name, hash and cap. Never the ciphertext, and never the plaintext.
        print(f"  key   {key[1]}\n  hash  {key[2] or '(none stored — cannot be revoked)'}"
              f"\n  cap   ${key[4]}/month")
    else:
        cap = accounts.tier_cap(tier)
        print(f"  no key — {'no cap for this tier' if cap is None else 'not yet minted'}")
    events = await (await conn.execute(
        """select action, outcome, detail, created_at from ai_key_events
            where account_id = %s order by created_at desc limit 5""",
        (account_id,))).fetchall()
    for action, outcome, detail, when in events:
        print(f"  {when:%Y-%m-%d %H:%M}  {action}/{outcome}  {detail or ''}")
    return 0


async def _grant(conn, wa_id: str, tier: str) -> int:
    row = await _user_by_wa_id(conn, wa_id)
    if not row:
        print(f"no user with wa_id {wa_id} — they must message the number first")
        return 1
    user_id, account_id, _, current = row
    if accounts.tier_cap(tier) is None:
        print(f"tier {tier!r} has no cap, so no key would be minted. "
              f"Use a tier from {sorted(k for k, v in accounts.TIER_CAPS.items() if v)}.")
        return 1

    account_id = account_id or await accounts.ensure_for_user(conn, user_id)
    await conn.execute("update accounts set tier = %s::account_tier where id = %s",
                       (tier, account_id))
    turn = await scheduling.enqueue(
        conn, user_id, "provision_key", datetime.now(timezone.utc),
        payload={"account_id": account_id},
        # One outstanding mint per account. The database enforces one *active
        # key*; this stops a second turn being queued while the first is due.
        dedupe_key=openrouter.provision_dedupe_key(account_id))
    print(f"account {account_id}: {current} -> {tier} (cap ${accounts.tier_cap(tier)}/month)")
    print("queued provisioning" if turn else "provisioning already queued")
    print("the worker mints on its next tick; check with --show")
    return 0


async def _revoke(conn, wa_id: str) -> int:
    row = await _user_by_wa_id(conn, wa_id)
    if not row or not row[1]:
        print(f"no account for wa_id {wa_id}")
        return 1
    done = await openrouter.revoke(conn, row[1])
    print("revoked" if done else "no active key to revoke")
    return 0


async def main() -> int:
    ap = argparse.ArgumentParser(description="Manage a tester's AI key")
    ap.add_argument("--wa-id", required=True, help="the tester's WhatsApp id")
    ap.add_argument("--tier", help=f"one of {sorted(accounts.TIER_CAPS)}")
    ap.add_argument("--show", action="store_true")
    ap.add_argument("--revoke", action="store_true")
    args = ap.parse_args()

    pool = db.pool()
    await pool.open()
    async with pool.connection() as conn:
        if args.revoke:
            return await _revoke(conn, args.wa_id)
        if args.tier:
            return await _grant(conn, args.wa_id, args.tier)
        return await _show(conn, args.wa_id)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
