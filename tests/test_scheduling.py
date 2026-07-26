"""One queue for all scheduled work. These protect the generalisation."""
import pytest
from datetime import datetime, timedelta, timezone
from saathi import scheduling
from saathi.worker import turns  # noqa: F401 - registers the kinds


class Cur:
    def __init__(self, rows=None): self._rows = rows or []
    async def fetchone(self): return self._rows[0] if self._rows else None
    async def fetchall(self): return self._rows


class Tx:
    async def __aenter__(self): return self
    async def __aexit__(self, *a): return False


class Conn:
    def __init__(self, claimed=None):
        self.sql = []; self.claimed = claimed or []
    def transaction(self): return Tx()
    async def execute(self, q, params=None):
        self.sql.append(" ".join(q.split()))
        if "update scheduled_turns t" in q:
            return Cur(self.claimed)
        if "returning id" in q.lower():
            return Cur([(11,)])
        return Cur()


class Pool:
    def __init__(self, conn): self.conn = conn
    def connection(self):
        outer = self
        class _C:
            async def __aenter__(self): return outer.conn
            async def __aexit__(self, *a): return False
        return _C()


# --- the generalisation itself ----------------------------------------------

def test_the_specced_kinds_are_registered():
    assert set(scheduling.registered()) >= {"reminder", "nudge", "checkin"}


def test_adding_a_kind_is_a_registration_not_a_worker_edit():
    """The architectural claim: the worker must not name individual kinds."""
    import inspect
    from saathi.worker import __main__ as w
    src = inspect.getsource(w)
    for kind in ("reminder", "nudge", "checkin"):
        assert f'"{kind}"' not in src, f"worker hardcodes {kind!r}"


def test_duplicate_kind_registration_is_refused():
    with pytest.raises(ValueError):
        scheduling.register("reminder", lambda *a, **k: None)


async def test_enqueue_refuses_an_unregistered_kind():
    """A row nobody can handle would sit pending forever, retrying silently."""
    with pytest.raises(ValueError) as e:
        await scheduling.enqueue(Conn(), 1, "telepathy",
                                 datetime.now(timezone.utc))
    assert "telepathy" in str(e.value) and "reminder" in str(e.value)


async def test_enqueue_stores_kind_payload_and_dedupe_key():
    conn = Conn()
    tid = await scheduling.enqueue(conn, 1, "nudge",
                                   datetime.now(timezone.utc) + timedelta(minutes=30),
                                   payload={"title": "dawa"}, dedupe_key="n:1")
    assert tid == 11
    assert any("insert into scheduled_turns" in s for s in conn.sql)


# --- claiming ----------------------------------------------------------------

async def test_claim_marks_in_the_same_statement():
    """No window where a row is claimed but unmarked."""
    assert "update scheduled_turns t" in scheduling.CLAIM_SQL
    assert "for update skip locked" in scheduling.CLAIM_SQL.lower()
    assert "returning" in scheduling.CLAIM_SQL.lower()


async def test_unknown_kind_on_a_claimed_row_fails_it_rather_than_looping():
    """A kind removed from the code must not retry forever."""
    conn = Conn(claimed=[(7, 1, "gone", {}, datetime.now(timezone.utc), 1)])
    n = await scheduling.run_once(Pool(conn))
    assert n == 0
    assert any("state='failed'" in s.replace(" ", "") or "state = 'failed'" in s
               for s in conn.sql)


async def test_a_failing_handler_is_retried_then_given_up_on():
    """Retrying forever turns a broken handler into a silent outage."""
    scheduling.register("boom", _boom)
    try:
        conn = Conn(claimed=[(9, 1, "boom", {}, datetime.now(timezone.utc), 1)])
        await scheduling.run_once(Pool(conn))
        assert any("state = %s" in s for s in conn.sql)     # released to pending

        conn2 = Conn(claimed=[(9, 1, "boom", {}, datetime.now(timezone.utc),
                               scheduling.MAX_ATTEMPTS)])
        await scheduling.run_once(Pool(conn2))
        assert any("last_error" in s for s in conn2.sql)
    finally:
        scheduling._KINDS.pop("boom", None)


async def _boom(conn, **kw):
    raise RuntimeError("handler exploded")


def test_max_attempts_is_bounded():
    assert 2 <= scheduling.MAX_ATTEMPTS <= 10


# --- the copy rule that is easy to violate ----------------------------------

def test_nudge_copy_is_not_constructible_in_code():
    """PRD §C2: never signal that the user forgot.

    The guarantee is structural, not editorial — the nudge sends an *approved
    Meta template* whose body is fixed, and the only thing code supplies is the
    reminder title. So no amount of careless string-building can produce "you
    missed yesterday's". This test pins that: the handler must reference the
    approved template and pass exactly one variable.
    """
    import inspect
    src = inspect.getsource(turns.nudge)
    assert "NUDGE_TEMPLATE" in src
    # exactly one variable handed to the template
    assert src.count("_handle(") == 1
    assert 'payload.get("title"' in src


def test_nudge_template_is_the_approved_utility_one():
    from saathi.wa.templates import TEMPLATES
    names = {t["name"] for t in TEMPLATES}
    assert turns.NUDGE_TEMPLATE in names
    spec = next(t for t in TEMPLATES if t["name"] == turns.NUDGE_TEMPLATE)
    assert spec["category"] == "UTILITY"
    body = next(c for c in spec["components"] if c["type"] == "BODY")["text"]
    for reproach in ("missed", "forgot", "bhool", "phir se"):
        assert reproach not in body.lower()


async def test_paused_user_is_not_messaged():
    class C(Conn):
        async def execute(self, q, params=None):
            self.sql.append(" ".join(q.split()))
            if "u.paused" in q:
                return Cur([("91999", "whatsapp", True)])   # paused
            return Cur()
    conn = C()
    sent = await turns._handle(conn, 1, "reminder_fire_v2", ["dawa"])
    assert sent is None
