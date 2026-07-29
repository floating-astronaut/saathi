"""PR-15 inbound admission, driven through the pipeline boundary."""
from datetime import datetime, timezone

import pytest

from saathi import pipeline, rate_limit
from saathi.channels import registry
from saathi.core import backpressure


class Cursor:
    def __init__(self, row=None): self.row = row
    async def fetchone(self): return self.row
    async def fetchall(self): return []
    rowcount = 1


class Conn:
    def __init__(self): self.sql = []
    async def execute(self, query, params=None):
        self.sql.append((" ".join(query.split()), params))
        low = query.lower()
        if "from user_channels c join users u" in low:
            return Cursor((5, 1, datetime.now(timezone.utc), "Kamala", "Asia/Kolkata", "auto", "active"))
        if "select 1 from messages" in low:
            return Cursor(None)
        if "from conversations" in low:
            return Cursor((7,))
        if "select onboarding" in low:
            return Cursor(("done",))
        if "returning id" in low:
            return Cursor((99,))
        return Cursor(None)


@pytest.fixture
def wire(monkeypatch):
    sent = []
    async def send_text(conn, uid, handle, text): sent.append(text); return "wamid.out"
    async def touch(conn, uid, at=None): return None
    async def history(conn, uid, limit=12): return []
    monkeypatch.setattr(registry.get("whatsapp"), "send_text", send_text)
    monkeypatch.setattr(pipeline.window, "touch", touch)
    monkeypatch.setattr(pipeline.conversation, "history", history)
    return sent


def message(mid="rate-1"):
    return {"id": mid, "from": "919812345678", "type": "text", "text": {"body": "hello"}}


async def test_duplicate_does_not_reserve_a_turn(wire, monkeypatch):
    async def seen(conn, mid): return True
    async def no_reserve(*args, **kwargs): raise AssertionError("duplicate consumed quota")
    monkeypatch.setattr(pipeline, "already_seen", seen)
    monkeypatch.setattr(rate_limit, "reserve", no_reserve)

    out = await pipeline.handle_message(Conn(), message())
    assert out == {"skipped": "duplicate"}


async def test_rate_limit_stops_before_agent_or_audio(wire, monkeypatch):
    async def deny(*args, **kwargs): return False
    async def notify(*args, **kwargs): return True
    async def boom(*args, **kwargs): raise AssertionError("agent ran after rate refusal")
    monkeypatch.setattr(rate_limit, "reserve", deny)
    monkeypatch.setattr(rate_limit, "claim_notice", notify)
    monkeypatch.setattr(pipeline.loop, "run", boom)

    out = await pipeline.handle_message(Conn(), message())
    assert out == {"skipped": "rate_limited"}
    assert len(wire) == 1 and "wait a minute" in wire[0].lower()


async def test_rate_limit_goes_quiet_after_its_one_notice(wire, monkeypatch):
    async def deny(*args, **kwargs): return False
    async def silent(*args, **kwargs): return False
    monkeypatch.setattr(rate_limit, "reserve", deny)
    monkeypatch.setattr(rate_limit, "claim_notice", silent)

    out = await pipeline.handle_message(Conn(), message())
    assert out == {"skipped": "rate_limited"}
    assert wire == []


async def test_global_busy_does_not_consume_user_quota(wire, monkeypatch):
    async def no_reserve(*args, **kwargs): raise AssertionError("busy turn consumed quota")
    async def notify(*args, **kwargs): return True
    monkeypatch.setattr(rate_limit, "reserve", no_reserve)
    monkeypatch.setattr(rate_limit, "claim_notice", notify)
    monkeypatch.setattr(pipeline, "_TURN_GATE", backpressure.Gate("turn", 1))
    held = pipeline._TURN_GATE.hold()
    held.__enter__()
    try:
        out = await pipeline.handle_message(Conn(), message())
    finally:
        held.__exit__(None, None, None)
    assert out == {"skipped": "busy"}
    assert len(wire) == 1 and "try again" in wire[0].lower()


async def test_reservation_sql_serializes_then_inserts():
    class ReservationConn:
        def __init__(self): self.calls = []
        async def execute(self, query, params=None):
            self.calls.append((query, params))
            if "pg_try_advisory_xact_lock" in query.lower():
                return Cursor((True,))
            return Cursor((True,)) if "select exists" in query.lower() else Cursor()

    conn = ReservationConn()
    assert await rate_limit.reserve(conn, 12, limit=6, window_seconds=60)
    assert "pg_try_advisory_xact_lock" in conn.calls[0][0]
    assert "insert into inbound_turn_admissions" in conn.calls[2][0].lower()


async def test_lock_contention_is_quiet_and_never_queues():
    class ContendedConn:
        async def execute(self, query, params=None):
            return Cursor((False,))

    assert await rate_limit.reserve(ContendedConn(), 12, limit=6, window_seconds=60) is None
