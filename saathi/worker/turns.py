"""The registered kinds of scheduled work.

Read top to bottom this is the list of everything the worker can be asked to do
in the future — the scheduling equivalent of `capabilities.py`.
"""
from __future__ import annotations

import logging

from datetime import datetime, timedelta, timezone

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


async def _settle(conn, turn_id: int, mid: str | None) -> None:
    """Record how a send ended. **Every handler that sends must call this.**

    `sweep_stuck` reclaims any turn left in 'sent' with no `wa_message_id`,
    because that is what a worker dying mid-send looks like. It cannot tell
    that from a handler that sent perfectly well and simply never wrote the id
    down — so a handler that skips this step has its message re-delivered every
    fifteen minutes until the attempt budget runs out.

    That is not hypothetical. `nudge` and `checkin` called `_handle` and
    discarded its return value, and on 2026-07-27 a live user received the same
    "time to sleep" nudge four times, twenty-three seconds to fifteen minutes
    apart, each one a genuine WhatsApp 200 OK. `reminder` had the write-back
    and the comment explaining why; the other two were written without either.
    Sharing the step is the point: it is no longer something a new handler can
    forget to remember.

    A `None` id means we *chose* not to send — the user is paused, or has no
    active handle. That is marked 'skipped' rather than left 'sent', or the
    sweep would retry a paused user's reminder forever.
    """
    if mid:
        await conn.execute(
            "update scheduled_turns set wa_message_id=%s where id=%s", (mid, turn_id))
    else:
        await conn.execute(
            "update scheduled_turns set state='skipped' where id=%s", (turn_id,))


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
    await _settle(conn, turn_id, mid)

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
    mid = await _handle(conn, user_id, NUDGE_TEMPLATE,
                        [payload.get("title", "aapka kaam")])
    await _settle(conn, turn_id, mid)


# --- stale handle lifecycle --------------------------------------------------

async def reverify(conn, *, turn_id, user_id, payload, scheduled_for):
    """Warn at day 60; revoke only after a full 90 days without inbound proof."""
    from .. import identity
    uc_id, stage = payload.get("user_channel_id"), payload.get("stage", "warn")
    row = await (await conn.execute(
        """select last_seen_at, status::text from user_channels
             where id=%s and user_id=%s and revoked_at is null""", (uc_id, user_id))).fetchone()
    if not row:
        await conn.execute("update scheduled_turns set state='skipped' where id=%s", (turn_id,))
        return
    last_seen, status = row
    now = datetime.now(timezone.utc)
    age = now - last_seen
    if stage == "warn":
        if age < identity.DORMANT_AFTER or status != "active":
            await identity.schedule_reverify(conn, user_id, uc_id, last_seen)
            await conn.execute("update scheduled_turns set state='skipped' where id=%s", (turn_id,))
            return
        # The approved generic check-in template is deliberately content-free;
        # it reopens the WhatsApp window without leaking who used this handle.
        mid = await _handle(conn, user_id, CHECKIN_TEMPLATE, ["Hello"])
        await _settle(conn, turn_id, mid)
        await scheduling.enqueue(
            conn, user_id, "reverify", last_seen + identity.REVOKE_AFTER,
            payload={"user_channel_id": uc_id, "stage": "revoke"},
            dedupe_key=f"reverify:revoke:{uc_id}:{int(last_seen.timestamp())}")
        return
    if age < identity.REVOKE_AFTER:
        await scheduling.enqueue(
            conn, user_id, "reverify", last_seen + identity.REVOKE_AFTER,
            payload={"user_channel_id": uc_id, "stage": "revoke"},
            dedupe_key=f"reverify:revoke:{uc_id}:{int(last_seen.timestamp())}")
        await conn.execute("update scheduled_turns set state='skipped' where id=%s", (turn_id,))
        return
    await conn.execute("update user_channels set revoked_at=now(), is_primary=false where id=%s", (uc_id,))
    await conn.execute("update scheduled_turns set state='acked', acked_at=now() where id=%s", (turn_id,))
    log.warning("revoked dormant handle %s for user %s after 90 days", uc_id, user_id)


# --- daily check-in ----------------------------------------------------------

async def checkin(conn, *, turn_id, user_id, payload, scheduled_for):
    """Open the free 24-hour window once a day (§11).

    A template's job is not to say everything — it is to get a reply.
    """
    n = await (await conn.execute(
        """select count(*) from reminders
            where user_id = %s and status = 'active' and deleted_at is null""",
        (user_id,))).fetchone()
    mid = await _handle(conn, user_id, CHECKIN_TEMPLATE, [str(n[0] if n else 0)])
    await _settle(conn, turn_id, mid)


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


# --- per-account AI key provisioning (AI-1) ----------------------------------

async def provision_key(conn, *, turn_id, user_id, payload, scheduled_for):
    """Mint this account's capped OpenRouter key.

    On the queue, and **never inside an onboarding turn**. Onboarding is
    deterministic and makes no model call on purpose — that property is what
    makes an open door safe — and a blocking third-party HTTP call on that path
    would regress it. Once this lands, the account's own key is available for model turns.

    This turn sends the user nothing, so it settles itself rather than calling
    `_settle`: there is no message id to record, and leaving it 'sent' would
    have the sweep reclaim and re-mint it every fifteen minutes.
    """
    from .. import openrouter
    account_id = payload.get("account_id")
    if not account_id:
        await conn.execute(
            "update scheduled_turns set state='skipped' where id=%s", (turn_id,))
        log.error("provision_key turn %s carried no account_id", turn_id)
        return
    try:
        result = await openrouter.mint(conn, account_id)
    except openrouter.ProvisioningDisabled as exc:
        # Configuration, not a transient fault. Retrying a missing env var five
        # times just delays the same answer.
        await conn.execute(
            "update scheduled_turns set state='failed', last_error=%s where id=%s",
            (str(exc)[:200], turn_id))
        log.error("provisioning disabled: %s", exc)
        return
    await conn.execute(
        "update scheduled_turns set state='acked' where id=%s", (turn_id,))
    log.info("provision_key turn %s: %s", turn_id, result)


scheduling.register("provision_key", provision_key)
scheduling.register("media_purge", media_purge)
scheduling.register("reminder", reminder)
scheduling.register("nudge", nudge)
scheduling.register("checkin", checkin)
scheduling.register("reverify", reverify)
