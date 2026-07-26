"""Conversation history shaping. The model rejects malformed turn sequences."""
import pytest
from saathi import conversation


class Cur:
    rowcount = 1
    def __init__(self, rows): self._rows = rows
    async def fetchall(self): return self._rows
    async def fetchone(self): return self._rows[0] if self._rows else None


class Conn:
    def __init__(self, rows): self.rows = rows; self.sql = []
    async def execute(self, q, params=None):
        self.sql.append(" ".join(q.split()))
        return Cur(self.rows)


async def test_history_is_oldest_first_with_roles_mapped():
    # stored newest-first, as the query returns it
    conn = Conn([("out", "reply two"), ("in", "hello two"),
                 ("out", "reply one"), ("in", "hello one")])
    h = await conversation.history(conn, 1)
    assert [m["role"] for m in h] == ["user", "assistant", "user"]
    assert h[0]["content"][0]["text"] == "hello one"


async def test_trailing_assistant_turn_is_dropped():
    """A tool loop rejects a conversation ending on an assistant turn."""
    conn = Conn([("out", "dangling"), ("in", "hi")])
    h = await conversation.history(conn, 1)
    assert h and h[-1]["role"] == "user"


async def test_consecutive_same_role_turns_are_collapsed():
    conn = Conn([("in", "third"), ("in", "second"), ("in", "first")])
    h = await conversation.history(conn, 1)
    assert [m["role"] for m in h] == ["user"]
    assert h[0]["content"][0]["text"] == "third"   # most recent wins


async def test_empty_history_is_empty_not_broken():
    assert await conversation.history(Conn([]), 1) == []


async def test_idle_threshold_lets_next_morning_continue_yesterday():
    assert conversation.IDLE_HOURS >= 24


async def test_delete_last_redacts_content_not_just_hides_it():
    conn = Conn([(1,)])
    await conversation.delete_last(conn, user_id=1, n=1)
    sql = " ".join(conn.sql)
    assert "deleted_at" in sql and "redacted_at" in sql
    assert "body_text = null" in sql and "transcript = null" in sql


async def test_clear_conversation_does_not_touch_facts_or_reminders():
    conn = Conn([(7,)])
    await conversation.clear_conversation(conn, user_id=1, conversation_id=7)
    sql = " ".join(conn.sql)
    assert "messages" in sql
    assert "facts" not in sql and "reminders" not in sql
