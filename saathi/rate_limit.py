"""Persistent inbound admission limits (PR-15).

This runs before transcription and capability dispatch.  ``messages`` cannot
serve as the counter: an audio message is only logged after its paid STT call.
Reservations therefore live in their own small, content-free table and are
serialized per user with a transaction-scoped PostgreSQL advisory lock.
"""
from __future__ import annotations


async def reserve(conn, user_id: int, *, limit: int, window_seconds: int) -> bool | None:
    """Reserve a turn; ``None`` means another request holds this user's lock."""
    if limit < 1 or window_seconds < 1:
        raise ValueError("rate-limit values must be positive")
    # The lock is deliberately before the count: concurrent webhooks for one
    # user must not both observe five of six slots and both admit themselves.
    # It must also be non-blocking: an admission queue is unbounded growth with
    # a friendlier name, and a delayed turn is no longer conversational.
    locked = await (await conn.execute(
        "select pg_try_advisory_xact_lock(%s)", (user_id,)
    )).fetchone()
    if locked is None:
        raise RuntimeError("rate-limit lock returned no result")
    if not locked[0]:
        return None
    await conn.execute(
        "delete from inbound_turn_admissions where user_id = %s "
        "and admitted_at < now() - (%s * interval '1 second')",
        (user_id, window_seconds),
    )
    row = await (await conn.execute(
        """with used as (
                 select count(*) as n from inbound_turn_admissions
                  where user_id = %s
                    and admitted_at >= now() - (%s * interval '1 second')
             ), inserted as (
                 insert into inbound_turn_admissions (user_id)
                 select %s from used where n < %s
                 returning id
             )
             select exists(select 1 from inserted)""",
        (user_id, window_seconds, user_id, limit),
    )).fetchone()
    if row is None:
        raise RuntimeError("rate-limit reservation returned no result")
    return bool(row[0])


async def claim_notice(conn, user_id: int, reason: str, *, cooldown_seconds: int) -> bool:
    """Return true at most once per user/reason cooldown, without retaining content."""
    if cooldown_seconds < 1:
        raise ValueError("notice cooldown must be positive")
    row = await (await conn.execute(
        """insert into inbound_limit_notices (user_id, reason, last_notified_at)
               values (%s, %s, now())
               on conflict (user_id, reason) do update
                     set last_notified_at = excluded.last_notified_at
                   where inbound_limit_notices.last_notified_at
                         < now() - (%s * interval '1 second')
               returning 1""",
        (user_id, reason, cooldown_seconds),
    )).fetchone()
    return row is not None
