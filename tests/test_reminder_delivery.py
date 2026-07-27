"""A reminder that is created must actually be dispatched.

These exist because it wasn't. `_create_reminder` wrote to `reminder_fires`,
the worker read only `scheduled_turns`, and the sole reader of `reminder_fires`
(`worker/reminder_scheduler.py`) was referenced nowhere in the repo. Every
reminder created after migration 006 went into a table nothing reads.

Nothing raised, no test failed, and both tables were empty in dev — so the
product's worst failure was one real user away and completely invisible.
"""
from saathi import scheduling
from saathi.agent.tools.handlers import Handlers, to_rrule
from saathi.worker import turns  # noqa: F401 - registers the kinds


class Cur:
    def __init__(self, rows=None): self._rows = rows or []
    async def fetchone(self): return self._rows[0] if self._rows else None
    async def fetchall(self): return self._rows


class Tx:
    async def __aenter__(self): return self
    async def __aexit__(self, *a): return False


class Conn:
    """Records SQL; answers selects from `rows` keyed by a substring."""

    def __init__(self, rows=None):
        self.sql: list[str] = []
        self.rows = rows or {}

    def transaction(self): return Tx()

    async def execute(self, q, params=None):
        flat = " ".join(q.split())
        self.sql.append(flat)
        for needle, rows in self.rows.items():
            if needle in flat:
                return Cur(rows)
        # Only an INSERT ... returning id hands back a new row id. The sweep
        # also ends in `returning`, with four columns — a looser match here
        # silently feeds it the wrong shape.
        if flat.lower().startswith("insert") and "returning id" in flat.lower():
            return Cur([(11,)])
        return Cur()

    def wrote(self, needle: str) -> bool:
        return any(needle in s for s in self.sql)


# --- the bug itself ----------------------------------------------------------


async def test_created_reminder_lands_on_the_queue_the_worker_reads():
    conn = Conn({"insert into reminders": [(7,)]})
    out = await Handlers(conn, user_id=3)._create_reminder(
        {"title": "BP ki dawai", "recurrence": "daily", "time_24h": "08:00"})

    assert out["reminder_id"] == 7
    assert conn.wrote("insert into scheduled_turns"), \
        "reminder was not enqueued onto scheduled_turns — it will never fire"


async def test_created_reminder_does_not_write_to_the_dead_table():
    """`reminder_fires` has no reader. Writing there is how the dose went missing."""
    conn = Conn({"insert into reminders": [(7,)]})
    await Handlers(conn, user_id=3)._create_reminder(
        {"title": "BP ki dawai", "recurrence": "daily", "time_24h": "08:00"})

    assert not conn.wrote("reminder_fires")



# --- recurrence --------------------------------------------------------------


async def test_recurring_reminder_books_its_next_occurrence():
    """Nothing else walks the rrule, so a daily reminder fired exactly once."""
    from datetime import datetime, timezone
    rrule = to_rrule("daily", "08:00")
    conn = Conn({
        "from reminders": [("BP ki dawai", rrule, "Asia/Kolkata")],
        "from user_channels": [],          # no active handle -> deliberate no-send
    })
    await turns.reminder(conn, turn_id=1, user_id=3,
                         payload={"reminder_id": 7},
                         scheduled_for=datetime(2026, 7, 27, 2, 30, tzinfo=timezone.utc))

    assert conn.wrote("insert into scheduled_turns"), "next occurrence not booked"
    assert conn.wrote("update reminders set next_fire_at")


async def test_deliberate_no_send_is_marked_skipped_not_left_sent():
    """Otherwise the sweep reclaims a paused user's reminder forever."""
    from datetime import datetime, timezone
    conn = Conn({
        "from reminders": [("BP ki dawai", None, "Asia/Kolkata")],
        "from user_channels": [],
    })
    await turns.reminder(conn, turn_id=1, user_id=3,
                         payload={"reminder_id": 7},
                         scheduled_for=datetime(2026, 7, 27, 2, 30, tzinfo=timezone.utc))

    assert conn.wrote("state='skipped'")


# --- the sweep ---------------------------------------------------------------


async def test_sweep_only_reclaims_turns_that_never_reached_whatsapp():
    """The safety property. `wa_message_id` is set only after a send returns one.

    Asserted on the SQL because it is the guard that stops the sweep resending
    a reminder the user already received.
    """
    conn = Conn()
    await scheduling.sweep_stuck(conn)
    sql = conn.sql[0]
    assert "wa_message_id is null" in sql
    assert "state = 'sent'" in sql


async def test_sweep_gives_up_once_attempts_are_exhausted():
    """Retrying forever is how a broken handler becomes a silent outage."""
    conn = Conn()
    await scheduling.sweep_stuck(conn)
    assert "'failed'" in conn.sql[0]
    assert "'pending'" in conn.sql[0]


async def test_a_tick_sweeps_before_it_claims():
    """A turn abandoned last tick must be claimable by this one."""
    conn = Conn()

    class Pool:
        def connection(self):
            class _C:
                async def __aenter__(_s): return conn
                async def __aexit__(_s, *a): return False
            return _C()

    await scheduling.run_once(Pool())
    swept = [i for i, s in enumerate(conn.sql) if "wa_message_id is null" in s]
    claimed = [i for i, s in enumerate(conn.sql) if "update scheduled_turns t" in s]
    assert swept and claimed
    assert swept[0] < claimed[0]
