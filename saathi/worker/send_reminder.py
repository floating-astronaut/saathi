"""What actually happens when a reminder comes due.

Fires the approved utility template, with quick-reply buttons carrying the fire
id so the ack path stays deterministic (see pipeline.handle_ack).

Design rule from PRD §C2, easy to violate by accident: the copy must never
signal repetition or imply the user forgot. The template body is fixed and
approved, so the only variable is the reminder title — which is what keeps that
rule enforceable rather than aspirational.
"""
from __future__ import annotations

import logging

from ..wa import client as wa

log = logging.getLogger("saathi.worker.send")

TEMPLATE = "reminder_fire_v2"


async def send(conn, fire_id: int, reminder_id: int, user_id: int, scheduled_for) -> None:
    row = await (await conn.execute(
        """select u.wa_id, r.title
             from reminders r join users u on u.id = r.user_id
            where r.id = %s""", (reminder_id,))).fetchone()
    if not row:
        log.warning("fire %s: reminder %s vanished", fire_id, reminder_id)
        return
    wa_id, title = row

    # Outside the 24h window this must be a template — which is the normal case
    # for a reminder, since the user is asleep or busy when it fires.
    mid = await wa.send_template(conn, user_id, wa_id, TEMPLATE, "en", [title])

    await conn.execute(
        "update reminder_fires set wa_message_id = %s where id = %s", (mid, fire_id))
    await conn.execute(
        """insert into messages (user_id, direction, kind, wa_message_id,
                                 body_text, template_name)
           values (%s,'out','template',%s,%s,%s)
           on conflict (wa_message_id) do nothing""",
        (user_id, mid, title, TEMPLATE))
    log.info("fired reminder %s for user %s", reminder_id, user_id)
