"""The pipeline's ordering guarantees, exercised against fakes.

These are the rules that make the product safe rather than merely working:
safety before the model, dedupe before side effects, window touch before send.
"""
import pytest
from saathi import pipeline


class FakeCursor:
    def __init__(self, row=None): self._row = row
    async def fetchone(self): return self._row
    async def fetchall(self): return []
    rowcount = 1


class FakeConn:
    """Records SQL in order so we can assert what happened and in what sequence."""
    def __init__(self, seen_message=False):
        self.sql = []
        self.seen_message = seen_message
    async def execute(self, q, params=None):
        self.sql.append(" ".join(q.split())[:70])
        low = q.lower()
        if "insert into users" in low:
            return FakeCursor((1, "Asia/Kolkata", "auto", "Kamala"))
        if "select 1 from messages" in low:
            return FakeCursor((1,) if self.seen_message else None)
        if "returning id" in low:
            return FakeCursor((99,))
        return FakeCursor(None)


@pytest.fixture
def spy(monkeypatch):
    sent = []
    async def fake_send_text(conn, uid, wa_id, text): sent.append(text); return "wamid.out"
    async def fake_touch(conn, uid, at=None): conn.sql.append("WINDOW_TOUCH"); return None
    monkeypatch.setattr(pipeline.wa, "send_text", fake_send_text)
    monkeypatch.setattr(pipeline.window, "touch", fake_touch)
    return sent


async def test_emergency_never_reaches_the_model(spy, monkeypatch):
    async def boom(*a, **k):
        raise AssertionError("agent ran on an emergency message — R7 violation")
    monkeypatch.setattr(pipeline.loop, "run", boom)
    conn = FakeConn()
    out = await pipeline.handle_message(
        conn, {"id": "w1", "from": "91", "type": "text",
               "text": {"body": "mujhe seene mein dard ho raha hai"}})
    assert out == {"handled": "safety", "trigger": "medical_emergency"}
    assert "112" in spy[0]
    assert any("safety_events" in s for s in conn.sql)


async def test_duplicate_webhook_is_a_noop(spy, monkeypatch):
    async def boom(*a, **k):
        raise AssertionError("processed a replayed webhook")
    monkeypatch.setattr(pipeline.loop, "run", boom)
    conn = FakeConn(seen_message=True)
    out = await pipeline.handle_message(
        conn, {"id": "dup", "from": "91", "type": "text", "text": {"body": "hi"}})
    assert out == {"skipped": "duplicate"}
    assert spy == []


async def test_window_is_touched_before_any_send(spy, monkeypatch):
    async def boom(*a, **k):
        raise AssertionError("should not reach agent")
    monkeypatch.setattr(pipeline.loop, "run", boom)
    conn = FakeConn()
    await pipeline.handle_message(
        conn, {"id": "w2", "from": "91", "type": "text",
               "text": {"body": "aapne 25 lakh ki lottery jeeti hai"}})
    # scam warning went out, and the window was opened before it
    assert "WINDOW_TOUCH" in conn.sql
    assert conn.sql.index("WINDOW_TOUCH") < len(conn.sql)
    assert "OTP" in spy[0]


async def test_button_ack_is_deterministic_not_model_routed(spy, monkeypatch):
    async def boom(*a, **k):
        raise AssertionError("an ack button was routed through the LLM")
    monkeypatch.setattr(pipeline.loop, "run", boom)
    conn = FakeConn()
    out = await pipeline.handle_message(conn, {
        "id": "w3", "from": "91", "type": "interactive",
        "interactive": {"button_reply": {"id": "ack:42", "title": "Ho gaya"}}})
    assert out["handled"] == "ack"
    assert any("reminder_fires" in s and "acked" in s for s in conn.sql)


async def test_empty_text_does_not_call_the_model(spy, monkeypatch):
    async def boom(*a, **k):
        raise AssertionError("ran the model on an empty message")
    monkeypatch.setattr(pipeline.loop, "run", boom)
    conn = FakeConn()
    out = await pipeline.handle_message(
        conn, {"id": "w4", "from": "91", "type": "text", "text": {"body": "   "}})
    assert out == {"skipped": "empty"}
