"""The registered kinds of scheduled work.

Read top to bottom this is the list of everything the worker can be asked to do
in the future — the scheduling equivalent of `capabilities.py`.
"""
from __future__ import annotations

import logging

from datetime import timedelta

from .. import scheduling
from ..channels import registry
from ..wa import client as wa

log = logging.getLogger("saathi.worker.turns")

REMINDER_TEMPLATE = "reminder_fire_v2"
NUDGE_TEMPLATE = "reminder_nudge_v2"
CHECKIN_TEMPLATE = "daily_checkin"

#: How long to wait before asking whether a reminder was acted on. Long enough
#: not to nag, short enough that a missed morning dose is still actionable.
NUDGE_AFTER_MINUTES = 20


async def _handle(conn, user_id: int, template: str, variables: list[str],
                  payloads: list[str] | None = None) -> str | None:
    """Send a utility template to a user, unless they have paused us."""
    row = await (await conn.execute(
        """select c.channel_user_id, c.channel::text, u.paused
             from user_channels c join users u on u.id = c.user_id
            where c.user_id = %s and c.is_primary and c.revoked_at is null
              and c.status = 'active'
            limit 1""", (user_id,))).fetchone()
    if not row:
        log.warning("user %s has no active primary handle", user_id)
        return None
    handle, channel, paused = row
    if paused:
        log.info("user %s is paused; not sending %s", user_id, template)
        return None
    transport = registry.get(channel)
    if not transport.capabilities.requires_templates:
        # A channel without a session window can just be messaged.
        return await transport.send_text(conn, user_id, handle, variables[0])
    return await wa.send_template(conn, user_id, handle, template, "en", variables,
                                  payloads=payloads or [])


# --- reminder ----------------------------------------------------------------

async def reminder(conn, *, turn_id, user_id, payload, scheduled_for):
    rid = payload.get("reminder_id")
    row = await (await conn.execute(
        """select title, rrule, tz from reminders
            where id = %s and status = 'active' and deleted_at is null""",
        (rid,))).fetchone()
    if not row:
        await conn.execute(
            "update scheduled_turns set state='skipped' where id=%s", (turn_id,))
        return
    title, rrule, tz = row

    # Payloads in template button order: "Ho gaya" then "15 min baad". Without
    # these the tap returns only the label and nothing ties it to this turn.
    mid = await _handle(conn, user_id, REMINDER_TEMPLATE, [title],
                        payloads=[f"ack:{turn_id}", f"snooze:{turn_id}:15"])
    if mid:
        await conn.execute(
            "update scheduled_turns set wa_message_id=%s where id=%s", (mid, turn_id))
    else:
        # We decided not to send — the user is paused, or has no active handle.
        # Mark it, because `sweep_stuck` reclaims turns left in 'sent' with no
        # message id, and it must be able to tell "chose not to send" from "the
        # send died halfway". Left as 'sent', a paused user's reminder would be
        # reclaimed and retried forever.
        await conn.execute(
            "update scheduled_turns set state='skipped' where id=%s", (turn_id,))

    # Follow up if it goes unacknowledged. Nothing enqueued a nudge before, so
    # the handler below was registered and dead and a missed dose was silent.
    if mid:
        await scheduling.enqueue(
            conn, user_id, "nudge",
            scheduled_for + timedelta(minutes=NUDGE_AFTER_MINUTES),
            payload={"origin_turn_id": turn_id, "title": title},
            dedupe_key=f"nudge:{turn_id}")

    # A recurring reminder has to book its own next occurrence: nothing else
    # walks the rrule. Without this a daily reminder fires exactly once.
    if rrule:
        await _schedule_next(conn, user_id, rid, rrule, tz, scheduled_for)
    log.info("fired reminder %s for user %s", rid, user_id)


async def _schedule_next(conn, user_id: int, rid: int, rrule: str, tz: str,
                         after) -> None:
    """Book the next occurrence of a recurring reminder.

    The dedupe key is (reminder, occurrence), so booking the same occurrence
    twice is a no-op at the unique index. That matters because `sweep_stuck`
    can reclaim a turn whose handler already got this far.
    """
    # Local import: `handlers` imports this module to register the kinds.
    from ..agent.tools.handlers import next_fire

    when = next_fire(rrule, tz, after=after)
    await scheduling.enqueue(
        conn, user_id, "reminder", when,
        payload={"reminder_id": rid},
        dedupe_key=f"reminder:{rid}:{when.isoformat()}",
    )
    await conn.execute(
        "update reminders set next_fire_at = %s where id = %s", (when, rid))


# --- nudge -------------------------------------------------------------------

async def nudge(conn, *, turn_id, user_id, payload, scheduled_for):
    """Follow up an unacknowledged reminder.

    PRD §C2: never signal that the user forgot. The approved copy asks whether
    it is done, and the only variable is the reminder title — which is what
    keeps that rule enforceable rather than aspirational.
    """
    origin = payload.get("origin_turn_id")
    if origin:
        row = await (await conn.execute(
            "select state::text from scheduled_turns where id = %s", (origin,))).fetchone()
        if row and row[0] in ("acked", "skipped"):
            await conn.execute(
                "update scheduled_turns set state='skipped' where id=%s", (turn_id,))
            return
    await _handle(conn, user_id, NUDGE_TEMPLATE, [payload.get("title", "aapka kaam")])


# --- daily check-in ----------------------------------------------------------

async def checkin(conn, *, turn_id, user_id, payload, scheduled_for):
    """Open the free 24-hour window once a day (§11).

    A template's job is not to say everything — it is to get a reply.
    """
    n = await (await conn.execute(
        """select count(*) from reminders
            where user_id = %s and status = 'active' and deleted_at is null""",
        (user_id,))).fetchone()
    await _handle(conn, user_id, CHECKIN_TEMPLATE, [str(n[0] if n else 0)])


# --- media retention ---------------------------------------------------------

async def media_purge(conn, *, turn_id, user_id, payload, scheduled_for):
    """Tidy media_blobs rows for objects S3 has already expired.

    S3 owns the deletion; this only stops the table growing without bound. It
    reschedules itself, which is the pattern any recurring maintenance should
    use now that the queue is general.
    """
    from .. import media_store
    n = await media_store.purge_expired(conn)
    from datetime import datetime, timedelta, timezone
    await scheduling.enqueue(conn, user_id, "media_purge",
                             datetime.now(timezone.utc) + timedelta(hours=6),
                             dedupe_key=f"purge:{datetime.now(timezone.utc):%Y%m%d%H}")
    log.info("media purge tidied %s rows", n)


scheduling.register("media_purge", media_purge)
scheduling.register("reminder", reminder)
scheduling.register("nudge", nudge)
scheduling.register("checkin", checkin)
