"""Reminder scheduler — Postgres as the job queue, no Redis.

Claims due fires with `FOR UPDATE SKIP LOCKED` so N worker processes never
double-send. This is the same pattern the MeshPilot v1 box has run in
production across ~20 workers; it holds well past 10k users.

Two correctness notes that cost real money to learn:
  * SKIP LOCKED only holds its row locks inside an explicit transaction. If you
    let psycopg autocommit the SELECT, the locks are released before you UPDATE
    and two workers can claim the same row. Hence the explicit transaction.
  * Claim and mark in one statement (UPDATE ... FROM (SELECT ... FOR UPDATE
    SKIP LOCKED) ... RETURNING) so there is no window where a row is claimed
    but not yet marked.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

log = logging.getLogger("saathi.worker.reminders")

POLL_SECONDS = 30
BATCH = 50

CLAIM_SQL = """
update reminder_fires f
   set state    = 'sent',
       attempts = f.attempts + 1,
       sent_at  = now()
  from (
        select id
          from reminder_fires
         where state = 'pending'
           and scheduled_for <= now()
         order by scheduled_for
         limit %s
           for update skip locked
       ) due
 where f.id = due.id
returning f.id, f.reminder_id, f.user_id, f.scheduled_for
"""


async def claim_due(conn, batch: int = BATCH) -> list[tuple]:
    """Atomically claim up to `batch` due fires. Caller must own a transaction."""
    cur = await conn.execute(CLAIM_SQL, (batch,))
    return await cur.fetchall()


async def release(conn, fire_id: int, error: str) -> None:
    """Hand a fire back after a send failure, so it is retried rather than lost."""
    await conn.execute(
        """update reminder_fires
              set state = 'pending', last_error = %s
            where id = %s""",
        (error[:500], fire_id),
    )


async def run_once(pool, send) -> int:
    """One scheduler tick. Returns how many fires were dispatched."""
    sent = 0
    async with pool.connection() as conn:
        async with conn.transaction():          # locks must outlive the SELECT
            claimed = await claim_due(conn)
        for fire_id, reminder_id, user_id, scheduled_for in claimed:
            try:
                await send(conn, fire_id, reminder_id, user_id, scheduled_for)
                sent += 1
            except Exception as exc:             # noqa: BLE001 - never lose a dose
                log.exception("fire %s failed", fire_id)
                async with conn.transaction():
                    await release(conn, fire_id, repr(exc))
    return sent


async def run_forever(pool, send) -> None:
    log.info("reminder scheduler up (poll=%ss batch=%s)", POLL_SECONDS, BATCH)
    while True:
        started = datetime.now(timezone.utc)
        try:
            n = await run_once(pool, send)
            if n:
                log.info("dispatched %s reminder(s)", n)
        except Exception:                        # noqa: BLE001
            log.exception("scheduler tick failed")
        elapsed = (datetime.now(timezone.utc) - started).total_seconds()
        await asyncio.sleep(max(1.0, POLL_SECONDS - elapsed))
