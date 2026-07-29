"""Every handler that sends must record that it sent.

On 2026-07-27 a live user received the same "Sone ka samay ho gaya hai 😴"
nudge four times — 15:55:59, 15:56:29, 16:11:29, 16:26:30 — each one a genuine
WhatsApp 200 OK. Nothing failed. `nudge` called `_handle` and discarded the
returned message id, so `sweep_stuck` (which reclaims 'sent' turns with a null
`wa_message_id`, because that is what a worker dying mid-send looks like) could
not tell a delivered nudge from an abandoned one, and re-sent it every fifteen
minutes until the attempt budget ran out. `checkin` had the same hole.

`reminder` had the write-back *and* a comment explaining exactly this hazard.
The defence existed and was simply not applied to two of the three senders,
which is why the assertions below are per-handler rather than one test of
`_settle`: what needs guarding is that no sender is forgotten.
"""
from datetime import datetime, timezone

import pytest

from saathi import scheduling
from saathi.worker import turns

UTC_NOON = datetime(2026, 7, 27, 12, 0, tzinfo=timezone.utc)

#: One active, unpaused primary handle — the shape `_handle` selects.
LIVE_HANDLE = [("919999999999", "whatsapp", False)]


class Cur:
    def __init__(self, rows=None): self._rows = rows or []
    async def fetchone(self): return self._rows[0] if self._rows else None
    async def fetchall(self): return self._rows


class Conn:
    def __init__(self, rows=None):
        self.sql: list[str] = []
        self.rows = rows or {}

    async def execute(self, q, params=None):
        flat = " ".join(q.split())
        self.sql.append(flat)
        for needle, rows in self.rows.items():
            if needle in flat:
                return Cur(rows)
        if flat.lower().startswith("insert") and "returning id" in flat.lower():
            return Cur([(11,)])
        return Cur()

    def wrote(self, needle: str) -> bool:
        return any(needle in s for s in self.sql)


@pytest.fixture
def delivered(monkeypatch):
    """A send that reaches WhatsApp and comes back with a message id."""
    async def _send(conn, user_id, handle, template, lang, variables, payloads=None):
        return "wamid.DELIVERED"
    monkeypatch.setattr(turns.wa, "send_template", _send)


def _conn_with_handle(extra=None):
    rows = {"from user_channels": LIVE_HANDLE}
    rows.update(extra or {})
    return Conn(rows)


# --- a delivered message must be recorded as delivered -----------------------

async def test_a_delivered_nudge_records_its_message_id(delivered):
    conn = _conn_with_handle()
    await turns.nudge(conn, turn_id=6, user_id=14,
                      payload={"title": "Sone ka samay ho gaya hai"},
                      scheduled_for=UTC_NOON)

    assert conn.wrote("set wa_message_id"), (
        "the nudge reached WhatsApp but did not record its id — the sweep will "
        "treat it as abandoned and re-send it every 15 minutes")


async def test_a_delivered_checkin_records_its_message_id(delivered):
    conn = _conn_with_handle({"count(*) from reminders": [(2,)]})
    await turns.checkin(conn, turn_id=9, user_id=14, payload={},
                        scheduled_for=UTC_NOON)

    assert conn.wrote("set wa_message_id")


async def test_a_delivered_reminder_records_its_message_id(delivered):
    conn = _conn_with_handle(
        {"from reminders": [("BP ki dawai", None, "Asia/Kolkata")]})
    await turns.reminder(conn, turn_id=1, user_id=14,
                         payload={"reminder_id": 7}, scheduled_for=UTC_NOON)

    assert conn.wrote("set wa_message_id")


# --- a deliberate no-send must not look like a crash ------------------------

async def test_an_unsent_nudge_is_skipped_rather_than_left_sent():
    # No active handle: we chose not to send. Left in 'sent', the sweep would
    # retry it until the budget ran out.
    conn = Conn({"from user_channels": []})
    await turns.nudge(conn, turn_id=6, user_id=14,
                      payload={"title": "Sone ka samay"}, scheduled_for=UTC_NOON)

    assert conn.wrote("state='skipped'")
    assert not conn.wrote("set wa_message_id")


async def test_an_unsent_checkin_is_skipped_rather_than_left_sent():
    conn = Conn({"from user_channels": [], "count(*) from reminders": [(0,)]})
    await turns.checkin(conn, turn_id=9, user_id=14, payload={},
                        scheduled_for=UTC_NOON)

    assert conn.wrote("state='skipped'")


async def test_a_paused_user_is_skipped_not_retried(delivered):
    # Paused is the third case: a live handle, but we must not message them.
    conn = Conn({"from user_channels": [("919999999999", "whatsapp", True)]})
    await turns.nudge(conn, turn_id=6, user_id=14,
                      payload={"title": "Sone ka samay"}, scheduled_for=UTC_NOON)

    assert conn.wrote("state='skipped'")


# --- an acknowledged reminder still must not leave its nudge dangling -------

async def test_a_nudge_skipped_for_an_acked_reminder_is_still_settled():
    conn = Conn({"state::text from scheduled_turns": [("acked",)]})
    await turns.nudge(conn, turn_id=6, user_id=14,
                      payload={"title": "x", "origin_turn_id": 5},
                      scheduled_for=UTC_NOON)

    assert conn.wrote("state='skipped'")


# --- the attempt budget -----------------------------------------------------

def test_attempts_are_capped_at_three():
    """Operator decision 2026-07-27: five deliveries felt like too many.

    Pinned because it is a number a refactor would happily change, and the
    person it is chosen for is the one holding the phone.
    """
    assert scheduling.MAX_ATTEMPTS == 3
