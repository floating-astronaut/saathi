"""Database-contract tests for the vendor usage ledger foundation."""
import pytest

from saathi import usage


class Cursor:
    def __init__(self, row=None, rowcount=0): self.row, self.rowcount = row, rowcount
    async def fetchone(self): return self.row


class Tx:
    async def __aenter__(self): return self
    async def __aexit__(self, *args): return False


class Conn:
    def __init__(self, *, existing=None, used=0):
        self.sql = []; self.existing = existing; self.used = used
    def transaction(self): return Tx()
    async def execute(self, query, params=None):
        self.sql.append((" ".join(query.split()), params))
        low = query.lower()
        if "pg_advisory_xact_lock" in low: return Cursor((None,))
        if "from vendor_usage_reservations where idempotency_key" in low:
            return Cursor(self.existing)
        if "coalesce(sum" in low: return Cursor((self.used,))
        if "insert into vendor_usage_reservations" in low:
            return Cursor((41, "held", params[7], params[0]))
        if "insert into vendor_usage_events" in low: return Cursor((77,))
        if "returning id" in low: return Cursor((1,))
        return Cursor(rowcount=3)


async def test_reservation_serializes_and_is_idempotent():
    conn = Conn(existing=(9, "held", 12, "wa:abc:llm"))
    out = await usage.reserve(conn, idempotency_key="wa:abc:llm", user_id=2,
                              account_id=8, vendor="bedrock", service="llm",
                              operation="converse", reserved_minor=12)
    assert out.id == 9
    assert "pg_advisory_xact_lock" in conn.sql[0][0]
    assert not any("insert into vendor_usage_reservations" in q.lower() for q, _ in conn.sql)


async def test_reservation_expires_holds_checks_cap_then_inserts():
    conn = Conn(used=80)
    out = await usage.reserve(conn, idempotency_key="wa:new:llm", user_id=2,
                              account_id=8, vendor="bedrock", service="llm",
                              operation="converse", reserved_minor=20, cap_minor=100)
    assert out.state == "held"
    sql = "\n".join(q for q, _ in conn.sql).lower()
    assert "state = 'expired'" in sql and "coalesce(sum" in sql
    assert "insert into vendor_usage_reservations" in sql


async def test_reservation_refuses_before_insert_when_cap_would_be_exceeded():
    conn = Conn(used=81)
    out = await usage.reserve(conn, idempotency_key="wa:cap:llm", user_id=2,
                              account_id=8, vendor="bedrock", service="llm",
                              operation="converse", reserved_minor=20, cap_minor=100)
    assert out is None
    assert not any("insert into vendor_usage_reservations" in q.lower() for q, _ in conn.sql)


async def test_settle_release_and_expiry_only_transition_held_rows():
    conn = Conn()
    assert await usage.settle(conn, 41, actual_minor=7)
    assert await usage.release(conn, 42)
    assert await usage.expire_holds(conn) == 3
    sql = "\n".join(q for q, _ in conn.sql).lower()
    assert sql.count("state = 'held'") == 3


async def test_event_is_content_free_json_and_vendor_request_idempotent():
    conn = Conn()
    event_id = await usage.record_event(
        conn, vendor="bedrock", service="llm", operation="converse", status="success",
        request_id="aws-request-1", units={"input_tokens": 3}, cost={"currency": "USD"},
        cost_source="catalog_estimate", metadata={"pricing_version": "2026-07"})
    assert event_id == 77
    sql, params = conn.sql[0]
    assert "on conflict (vendor, request_id)" in sql.lower()
    assert "prompt" not in sql.lower() and "transcript" not in sql.lower()
    assert all("hello" not in str(p).lower() for p in params)


async def test_unknown_cost_source_is_refused():
    with pytest.raises(ValueError):
        await usage.record_event(Conn(), vendor="bedrock", service="llm",
                                 operation="converse", status="success", cost_source="made_up")


def test_sarvam_stt_catalog_uses_integer_paise_and_request_rounding():
    assert usage.sarvam_stt_cost_paise(0) == 0
    assert usage.sarvam_stt_cost_paise(1) == 1
    assert usage.sarvam_stt_cost_paise(60) == 50
    assert usage.sarvam_stt_cost_paise(3600) == 3000


@pytest.mark.parametrize("kwargs", [
    {"idempotency_key": "", "account_id": 1, "reserved_minor": 1},
    {"idempotency_key": "x", "account_id": 0, "reserved_minor": 1},
    {"idempotency_key": "x", "account_id": 1, "reserved_minor": -1},
])
async def test_invalid_reservation_is_rejected(kwargs):
    with pytest.raises(ValueError):
        await usage.reserve(Conn(), user_id=1, vendor="bedrock", service="llm",
                            operation="converse", **kwargs)
