"""Identity, and how someone proves they are it.

There is no login. Nothing here should be read as "the phone number is the
account" — it explicitly is not:

  * A **user** is the identity. It owns memory, facts, reminders, consent.
  * A **channel handle** (WhatsApp wa_id, Telegram user id, …) is a *revocable
    claim* on that identity. Auth is "you demonstrably control this handle".
  * Handles are plural and replaceable. One person can hold several; a handle
    can be revoked and re-issued to someone else.

Why this shape rather than `users.wa_id`:

**Number recycling.** India permits recycling a disconnected mobile after ~90
days. If the number *were* the identity, the next person to hold it would
inherit an elder's medicine list, doctor and family. Because a handle is a claim
with a `last_seen_at` and a `revoked_at`, a long-dormant handle that suddenly
speaks is treated as a re-verification event rather than a returning user.

**Channel portability.** WhatsApp is a transport, not the product. When Telegram
or Discord arrives, the same identity carries the same memory — linked by a code
delivered on an already-trusted channel, never by matching a name or a number.
"""
from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

log = logging.getLogger("saathi.identity")

# A handle silent this long is not assumed to be the same human on its return.
# 90 days is when Indian recycling becomes possible; we re-verify well inside it.
DORMANT_AFTER = timedelta(days=60)
LINK_CODE_TTL = timedelta(minutes=15)


@dataclass(frozen=True)
class Resolved:
    user_id: int
    user_channel_id: int
    display_name: str | None
    tz: str
    voice_reply_pref: str
    is_new: bool
    # True when the handle has been silent past DORMANT_AFTER. The caller should
    # re-establish who this is before exposing stored personal facts.
    needs_reverification: bool
    #: 'pending' handles have not been admitted; the agent must not run for them.
    status: str = "active"


async def resolve(conn, channel: str, channel_user_id: str,
                  display_name: str | None = None,
                  phone_e164: str | None = None,
                  dm_policy: str = "pairing") -> Resolved:
    """Find or create the identity behind a channel handle.

    Returns `needs_reverification=True` when the handle is dormant — the caller
    must not leak stored facts until the person is re-established.
    """
    row = await (await conn.execute(
        """select c.id, c.user_id, c.last_seen_at, u.display_name, u.tz,
                  u.voice_reply_pref, c.status::text
             from user_channels c join users u on u.id = c.user_id
            where c.channel = %s and c.channel_user_id = %s and c.revoked_at is null""",
        (channel, channel_user_id),
    )).fetchone()

    if row:
        uc_id, user_id, last_seen, name, tz, voice, status = row
        dormant = (datetime.now(timezone.utc) - last_seen) > DORMANT_AFTER
        await conn.execute(
            """update user_channels
                  set last_seen_at = now(),
                      display_name = coalesce(%s, display_name)
                where id = %s""",
            (display_name, uc_id))
        if display_name:
            await conn.execute(
                "update users set display_name = coalesce(%s, display_name) where id = %s",
                (display_name, user_id))
        if dormant:
            log.warning("handle %s/%s dormant since %s — re-verification required",
                        channel, channel_user_id, last_seen)
        return Resolved(user_id, uc_id, display_name or name, tz, voice,
                        is_new=False, needs_reverification=dormant, status=status)

    # First contact on this handle: new identity, handle becomes its primary.
    user_id = (await (await conn.execute(
        """insert into users (wa_id, display_name) values (%s, %s)
           on conflict (wa_id) do update set display_name =
                coalesce(excluded.display_name, users.display_name)
           returning id""",
        (channel_user_id if channel == "whatsapp" else f"{channel}:{channel_user_id}",
         display_name),
    )).fetchone())[0]

    # Under a pairing policy a brand-new handle starts pending: the identity
    # exists so we can count and rate-limit it, but the agent will not run.
    new_status = "pending" if dm_policy == "pairing" else "active"
    uc_id = (await (await conn.execute(
        """insert into user_channels
             (user_id, channel, channel_user_id, phone_e164, display_name,
              status, is_primary, verified_at)
           values (%s,%s,%s,%s,%s,%s,
                   not exists (select 1 from user_channels
                                where user_id = %s and is_primary and revoked_at is null),
                   now())
           returning id""",
        (user_id, channel, channel_user_id, phone_e164, display_name,
         new_status, user_id),
    )).fetchone())[0]

    r = await (await conn.execute(
        "select tz, voice_reply_pref from users where id = %s", (user_id,))).fetchone()
    log.info("new identity %s via %s", user_id, channel)
    return Resolved(user_id, uc_id, display_name, r[0], r[1],
                    is_new=True, needs_reverification=False, status=new_status)


async def mark_verified(conn, user_channel_id: int) -> None:
    """Record that the human behind this handle was re-established just now."""
    await conn.execute(
        "update user_channels set verified_at = now(), last_seen_at = now() where id = %s",
        (user_channel_id,))


async def revoke(conn, channel: str, channel_user_id: str, reason: str = "") -> int:
    """Release a handle — number changed hands, or the user asked us to forget it.

    Revoking frees the handle so a *different* person can claim it later without
    ever seeing the previous holder's data. The identity itself is untouched.
    """
    cur = await conn.execute(
        """update user_channels set revoked_at = now()
            where channel = %s and channel_user_id = %s and revoked_at is null""",
        (channel, channel_user_id))
    log.info("revoked %s/%s (%s): %s rows", channel, channel_user_id, reason, cur.rowcount)
    return cur.rowcount


# --- linking a second channel ------------------------------------------------

async def issue_link_code(conn, user_id: int, channel: str) -> str:
    """Mint a short code to be delivered on a channel the user already controls.

    Deliberately not derivable from anything public: linking on a matching phone
    number or display name would let anyone claim someone else's memory.
    """
    code = f"{secrets.randbelow(1_000_000):06d}"
    await conn.execute(
        """insert into channel_link_codes (code, user_id, channel, expires_at)
           values (%s,%s,%s, now() + %s)""",
        (code, user_id, channel, LINK_CODE_TTL))
    return code


async def redeem_link_code(conn, code: str, channel: str, channel_user_id: str,
                           display_name: str | None = None) -> int | None:
    """Attach a new handle to the identity that issued the code.

    Returns the user_id on success, None if the code is unknown, expired, already
    used, or was issued for a different channel.
    """
    row = await (await conn.execute(
        """update channel_link_codes set consumed_at = now()
            where code = %s and channel = %s
              and consumed_at is null and expires_at > now()
        returning user_id""",
        (code, channel))).fetchone()
    if not row:
        return None
    user_id = row[0]
    await conn.execute(
        """insert into user_channels
             (user_id, channel, channel_user_id, display_name, verified_at)
           values (%s,%s,%s,%s, now())
           on conflict do nothing""",
        (user_id, channel, channel_user_id, display_name))
    log.info("linked %s/%s to identity %s", channel, channel_user_id, user_id)
    return user_id


# --- admission ---------------------------------------------------------------

ADMISSION_REPLY = (
    "Namaste! Main Saathi hoon. Aapko shuru karne ke liye ek code chahiye — "
    "jis family member ne yeh set up kiya hai, unse poochh lijiye.\n\n"
    "Hello! I'm Saathi. To get started you need a code — please ask the family "
    "member who set this up."
)


async def admit(conn, user_channel_id: int) -> None:
    """Mark a handle admitted. Called after a valid pairing code is redeemed."""
    await conn.execute(
        """update user_channels set status = 'active', verified_at = now()
            where id = %s""", (user_channel_id,))


async def should_explain(conn, user_channel_id: int, max_replies: int) -> bool:
    """Whether to send the pairing explanation again.

    Rate-limited on purpose: each reply costs money, and an unknown number
    messaging repeatedly must not be able to make us send without limit. We go
    quiet rather than argue.
    """
    row = await (await conn.execute(
        "select admission_replies from user_channels where id = %s",
        (user_channel_id,))).fetchone()
    if not row or row[0] >= max_replies:
        return False
    await conn.execute(
        """update user_channels
              set admission_replies = admission_replies + 1, admission_last_at = now()
            where id = %s""", (user_channel_id,))
    return True
