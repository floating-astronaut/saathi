"""The registered kinds of scheduled work.

Read top to bottom this is the list of everything the worker can be asked to do
in the future — the scheduling equivalent of `capabilities.py`.
"""
from __future__ import annotations

import logging

from .. import scheduling
from ..channels import registry
from ..wa import client as wa

log = logging.getLogger("saathi.worker.turns")

REMINDER_TEMPLATE = "reminder_fire_v2"
NUDGE_TEMPLATE = "reminder_nudge_v2"
CHECKIN_TEMPLATE = "daily_checkin"


async def _handle(conn, user_id: int, template: str, variables: list[str]) -> str | None:
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
    return await wa.send_template(conn, user_id, handle, template, "en", variables)


# --- reminder ----------------------------------------------------------------

async def reminder(conn, *, turn_id, user_id, payload, scheduled_for):
    rid = payload.get("reminder_id")
    row = await (await conn.execute(
        "select title from reminders where id = %s and status = 'active'", (rid,))).fetchone()
    if not row:
        await conn.execute(
            "update scheduled_turns set state='skipped' where id=%s", (turn_id,))
        return
    mid = await _handle(conn, user_id, REMINDER_TEMPLATE, [row[0]])
    if mid:
        await conn.execute(
            "update scheduled_turns set wa_message_id=%s where id=%s", (mid, turn_id))
    log.info("fired reminder %s for user %s", rid, user_id)


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


scheduling.register("reminder", reminder)
scheduling.register("nudge", nudge)
scheduling.register("checkin", checkin)
