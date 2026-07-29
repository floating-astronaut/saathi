"""A fired reminder must be able to come back.

Until 2026-07-28 the loop was open at every joint: the template carried no
per-message payload, the arriving "button" message type was never read, the ack
updated a table nothing fired from, and nothing ever enqueued a nudge. Each
break was silent, and together they meant §15's acknowledgement rate was
structurally zero rather than low.
"""
from datetime import datetime, timezone

from saathi.wa import client
from saathi.worker import turns


class Cur:
    def __init__(self, rows=None): self._rows = rows or []
    async def fetchone(self): return self._rows[0] if self._rows else None
    async def fetchall(self): return self._rows


class Conn:
    def __init__(self, rows=None):
        self.sql: list[str] = []; self.params: list = []; self.rows = rows or {}
    async def execute(self, q, params=None):
        flat = " ".join(q.split()); self.sql.append(flat); self.params.append(params)
        for needle, r in self.rows.items():
            if needle in flat: return Cur(r)
        if flat.lower().startswith("insert") and "returning id" in flat.lower():
            return Cur([(99,)])
        return Cur()
    def wrote(self, n): return any(n in s for s in self.sql)


# --- the payload the template carries ----------------------------------------

async def test_template_payloads_become_button_components(monkeypatch):
    """Without these a quick-reply returns only its label, and nothing ties the
    tap to the turn that produced it."""
    sent = {}

    class Resp:
        status_code = 200; text = ""
        def raise_for_status(self): pass
        def json(self): return {"messages": [{"id": "wamid.T"}]}

    class HTTP:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, url, headers=None, json=None):
            sent.update(json); return Resp()

    monkeypatch.setattr(client.httpx, "AsyncClient", lambda **kw: HTTP())
    async def _ok(*a, **k): return None
    monkeypatch.setattr(client, "assert_can_send", _ok)

    await client.send_template(Conn(), 1, "+911", "reminder_fire_v2", "en",
                               ["BP ki dawai"], payloads=["ack:7", "snooze:7:15"])

    comps = sent["template"]["components"]
    btns = [c for c in comps if c["type"] == "button"]
    assert len(btns) == 2, "both quick-reply buttons need a payload"
    assert btns[0]["sub_type"] == "quick_reply" and btns[0]["index"] == "0"
    assert btns[0]["parameters"][0]["payload"] == "ack:7"
    assert btns[1]["index"] == "1"
    assert btns[1]["parameters"][0]["payload"] == "snooze:7:15"


async def test_a_template_with_no_payloads_grows_no_buttons(monkeypatch):
    """Check-ins must not sprout buttons they were not approved with."""
    sent = {}
    class Resp:
        status_code = 200; text = ""
        def raise_for_status(self): pass
        def json(self): return {"messages": [{"id": "wamid.C"}]}
    class HTTP:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, url, headers=None, json=None):
            sent.update(json); return Resp()
    monkeypatch.setattr(client.httpx, "AsyncClient", lambda **kw: HTTP())
    async def _ok(*a, **k): return None
    monkeypatch.setattr(client, "assert_can_send", _ok)
    await client.send_template(Conn(), 1, "+911", "daily_checkin", "en", ["3"])
    assert not [c for c in sent["template"]["components"] if c["type"] == "button"]


# --- the loop closes ---------------------------------------------------------

async def test_firing_a_reminder_books_a_nudge():
    """The nudge handler was registered and dead — nothing enqueued one, so an
    unacknowledged reminder was never followed up."""
    conn = Conn({
        "from reminders": [("BP ki dawai", None, "Asia/Kolkata")],
        "from user_channels": [("+911", "whatsapp", False)],
    })
    class FakeTransport:
        class capabilities: requires_templates = False
        async def send_text(self, *a, **k): return "wamid.X"
    import saathi.channels.registry as reg
    orig = reg.get
    reg.get = lambda ch: FakeTransport()
    try:
        await turns.reminder(conn, turn_id=7, user_id=1,
                             payload={"reminder_id": 3},
                             scheduled_for=datetime(2026, 7, 28, 2, 30, tzinfo=timezone.utc))
    finally:
        reg.get = orig
    assert conn.wrote("insert into scheduled_turns"), "no nudge was enqueued"
    assert any(p and "nudge:7" in str(p) for p in conn.params), \
        "the nudge must be dedupe-keyed on the origin turn"


async def test_nudge_is_skipped_once_the_reminder_is_acked():
    """Being nudged about something you already confirmed is exactly the
    'signals that you forgot' failure PRD §C2 forbids."""
    conn = Conn({"select state::text from scheduled_turns": [("acked",)]})
    await turns.nudge(conn, turn_id=8, user_id=1,
                      payload={"origin_turn_id": 7, "title": "BP ki dawai"},
                      scheduled_for=datetime(2026, 7, 28, 2, 50, tzinfo=timezone.utc))
    assert conn.wrote("state='skipped'")
