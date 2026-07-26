"""Scheduled work of any kind, on one queue.

The worker used to know about reminders. Nudges, daily check-ins and dormancy
re-verification are all specced, and each would have added a branch — the same
shape we removed from the inbound path.

So a *kind* of scheduled work registers a handler, exactly as a capability
registers with the inbound chain:

    register("nudge", send_nudge)

and `enqueue(conn, user_id, "nudge", when, payload=...)` puts one on the queue.
The worker does not know what a nudge is.

Two correctness notes that cost real money to learn elsewhere, carried over
from the reminder scheduler:

  * `FOR UPDATE SKIP LOCKED` only holds its row locks inside an explicit
    transaction. Let the SELECT autocommit and two workers claim the same row.
  * Claim and mark in one statement, so there is no window where a row is
    claimed but not yet marked.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Awaitable, Callable

log = logging.getLogger("saathi.scheduling")

POLL_SECONDS = 30
BATCH = 50
MAX_ATTEMPTS = 5

#: kind -> handler(conn, turn) -> None
TurnHandler = Callable[..., Awaitable[None]]
_KINDS: dict[str, TurnHandler] = {}


def register(kind: str, handler: TurnHandler) -> None:
    if kind in _KINDS:
        raise ValueError(f"scheduled turn kind {kind!r} already registered")
    _KINDS[kind] = handler


def registered() -> list[str]:
    return sorted(_KINDS)


def clear() -> None:
    """Test seam only."""
    _KINDS.clear()


async def enqueue(conn, user_id: int, kind: str, when: datetime,
                  payload: dict | None = None, dedupe_key: str | None = None) -> int | None:
    """Schedule one turn. Returns its id, or None if deduped away.

    Refuses an unregistered kind loudly: a row nobody can handle would sit
    pending forever, retrying and failing silently, which is the worst of both.
    """
    if kind not in _KINDS:
        raise ValueError(f"no handler registered for scheduled kind {kind!r}; "
                         f"have {registered()}")
    row = await (await conn.execute(
        """insert into scheduled_turns (user_id, kind, payload, scheduled_for, dedupe_key)
           values (%s,%s,%s,%s,%s)
           on conflict do nothing
           returning id""",
        (user_id, kind, json.dumps(payload or {}), when, dedupe_key),
    )).fetchone()
    return row[0] if row else None


CLAIM_SQL = """
update scheduled_turns t
   set state    = 'sent',
       attempts = t.attempts + 1,
       sent_at  = now()
  from (
        select id from scheduled_turns
         where state = 'pending' and scheduled_for <= now()
         order by scheduled_for
         limit %s
           for update skip locked
       ) due
 where t.id = due.id
returning t.id, t.user_id, t.kind, t.payload, t.scheduled_for, t.attempts
"""


async def claim_due(conn, batch: int = BATCH) -> list[tuple]:
    """Atomically claim up to `batch` due turns. Caller must own a transaction."""
    return await (await conn.execute(CLAIM_SQL, (batch,))).fetchall()


async def release(conn, turn_id: int, error: str, attempts: int) -> None:
    """Hand a turn back after failure — or give up loudly once it is hopeless.

    Retrying forever is how a broken handler turns into thousands of rows and a
    silent outage. After MAX_ATTEMPTS the row is marked failed so it stops
    consuming the queue and shows up in any sweep for stuck work.
    """
    state = "failed" if attempts >= MAX_ATTEMPTS else "pending"
    await conn.execute(
        "update scheduled_turns set state = %s, last_error = %s where id = %s",
        (state, error[:500], turn_id))
    if state == "failed":
        log.error("turn %s gave up after %s attempts: %s", turn_id, attempts, error[:200])


async def run_once(pool) -> int:
    """One scheduler tick. Returns how many turns were dispatched."""
    done = 0
    async with pool.connection() as conn:
        async with conn.transaction():          # locks must outlive the SELECT
            claimed = await claim_due(conn)
        for turn_id, user_id, kind, payload, scheduled_for, attempts in claimed:
            handler = _KINDS.get(kind)
            if handler is None:
                # A kind vanished from the code while rows remain. Do not retry
                # forever against a handler that does not exist.
                async with conn.transaction():
                    await conn.execute(
                        "update scheduled_turns set state='failed', last_error=%s where id=%s",
                        (f"no handler for kind {kind!r}", turn_id))
                log.error("turn %s: unknown kind %r", turn_id, kind)
                continue
            try:
                await handler(conn, turn_id=turn_id, user_id=user_id,
                              payload=payload or {}, scheduled_for=scheduled_for)
                done += 1
            except Exception as exc:  # noqa: BLE001 - never lose a dose
                log.exception("turn %s (%s) failed", turn_id, kind)
                async with conn.transaction():
                    await release(conn, turn_id, repr(exc), attempts)
    return done
