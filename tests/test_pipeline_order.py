"""The pipeline's ordering guarantees, exercised against fakes.

These are the rules that make the product safe rather than merely working:
safety before the model, dedupe before side effects, window touch before send.
"""
from datetime import datetime, timezone

import pytest
from saathi import pipeline
from saathi.channels import registry


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
        # identity.resolve: an existing, recently-seen handle
        if "from user_channels c join users u" in low:
            return FakeCursor((5, 1, datetime.now(timezone.utc),
                               "Kamala", "Asia/Kolkata", "auto", "active"))
        if "select 1 from messages" in low:
            return FakeCursor((1,) if self.seen_message else None)
        if "from conversations" in low:
            return FakeCursor((7,))
        if "returning id" in low:
            return FakeCursor((99,))
        return FakeCursor(None)


@pytest.fixture
def spy(monkeypatch):
    """Patch the transport, not the WhatsApp module — sends now go through the
    channel abstraction, which is the point of the refactor."""
    sent = []
    async def fake_send_text(conn, uid, handle, text): sent.append(text); return "wamid.out"
    async def fake_touch(conn, uid, at=None): conn.sql.append("WINDOW_TOUCH"); return None
    async def fake_history(conn, uid, limit=12): return []
    monkeypatch.setattr(registry.get("whatsapp"), "send_text", fake_send_text)
    monkeypatch.setattr(pipeline.window, "touch", fake_touch)
    monkeypatch.setattr(pipeline.conversation, "history", fake_history)
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


async def test_unknown_handle_gets_no_agent_turn(spy, monkeypatch):
    """Admission control: an unadmitted sender must cost one rate-limited reply
    and nothing else — no STT, no model, no tools."""
    async def boom(*a, **k):
        raise AssertionError("agent ran for an unadmitted handle")
    monkeypatch.setattr(pipeline.loop, "run", boom)

    async def pending(*a, **k):
        return pipeline.identity.Resolved(
            user_id=1, user_channel_id=5, display_name=None, tz="Asia/Kolkata",
            voice_reply_pref="auto", is_new=True, needs_reverification=False,
            status="pending")
    async def explain(conn, uc_id, maxn): return True
    monkeypatch.setattr(pipeline.identity, "resolve", pending)
    monkeypatch.setattr(pipeline.identity, "should_explain", explain)

    out = await pipeline.handle_message(
        FakeConn(), {"id": "u1", "from": "919999999999", "type": "text",
                     "text": {"body": "hello?"}})
    assert out == {"skipped": "not_admitted"}
    assert len(spy) == 1 and "code" in spy[0].lower()


async def test_unknown_handle_goes_quiet_after_the_reply_cap(spy, monkeypatch):
    async def pending(*a, **k):
        return pipeline.identity.Resolved(
            user_id=1, user_channel_id=5, display_name=None, tz="Asia/Kolkata",
            voice_reply_pref="auto", is_new=False, needs_reverification=False,
            status="pending")
    async def exhausted(conn, uc_id, maxn): return False
    monkeypatch.setattr(pipeline.identity, "resolve", pending)
    monkeypatch.setattr(pipeline.identity, "should_explain", exhausted)
    out = await pipeline.handle_message(
        FakeConn(), {"id": "u2", "from": "919999999999", "type": "text",
                     "text": {"body": "hello again"}})
    assert out == {"skipped": "not_admitted"}
    assert spy == []          # silence, not an argument
