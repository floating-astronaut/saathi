"""A blank message row must never become a blank ContentBlock.

Production, 2026-07-27: four crashed turns between 08:05 and 08:28.

    ValidationException: The text field in the ContentBlock object at
    messages.N.content.0 is blank. Add text to the text field, and try again.

The `N` varied — 0, 1 and 2 — which was the clue. It was not the *incoming*
message that was blank (the agent capability already refuses to run on empty
text); it was a row in the **history** loaded ahead of it.

`messages.id = 55`: user 15 sent an image with no caption at 08:02:17, and it
was stored with `body_text = ''`. `conversation.history` filtered on
`is not null`, and an empty string is not null. Every turn that user took for
the next twenty-six minutes loaded that row, built `{"text": ""}`, and had the
whole turn rejected — so they got no reply at all, four times, with nothing in
the logs naming the cause.

Two guards, because there were two failures: the row should not have been
written, *and* it should not have been loaded. Rows like it already exist.
"""
import pytest

from saathi import conversation, pipeline


class Cur:
    def __init__(self, rows=None): self._rows = rows or []
    async def fetchone(self): return self._rows[0] if self._rows else None
    async def fetchall(self): return self._rows


class Conn:
    """Fake connection that *honours the blank filter* rather than ignoring it.

    Deliberate: a fake which returns its fixture regardless of the WHERE clause
    would pass whether or not the guard exists, which is precisely the class of
    test that let the original bug ship. Here, removing `<> ''` from the query
    stops the filtering and a blank block reaches the assertion.

    Rows are supplied newest-first, because the real query is `order by
    created_at desc` and `history` reverses them.
    """

    def __init__(self, rows=None):
        self.sql: list[str] = []
        self.params: list[tuple] = []
        self.rows = rows or {}

    async def execute(self, q, params=None):
        flat = " ".join(q.split())
        self.sql.append(flat)
        self.params.append(params or ())
        for needle, r in self.rows.items():
            if needle in flat:
                if "<> ''" in flat:                      # what Postgres would do
                    r = [row for row in r if row[1] and row[1].strip()]
                return Cur(r)
        if flat.lower().startswith("insert") and "returning id" in flat.lower():
            return Cur([(1,)])
        return Cur()


# --- the load side ----------------------------------------------------------

async def test_history_never_yields_a_blank_content_block():
    """The guard that would have stopped the outage.

    Row 55 is the `("in", "")` below: a captionless image sitting in the middle
    of an otherwise healthy conversation.
    """
    conn = Conn({"from messages": [
        ("in", "aur batao"), ("out", "namaste"), ("in", ""), ("in", "  "),
        ("in", "dawai yaad dilana"),
    ]})
    out = await conversation.history(conn, user_id=15)

    assert out, "everything was filtered — the fix went too far"
    for turn in out:
        for block in turn["content"]:
            assert block["text"].strip(), f"blank ContentBlock survived: {turn!r}"


async def test_history_still_returns_real_turns():
    conn = Conn({"from messages": [
        ("in", "aur batao"), ("out", "theek hai"), ("in", "dawai yaad dilana"),
    ]})
    out = await conversation.history(conn, user_id=15)
    assert [t["role"] for t in out] == ["user", "assistant", "user"]
    assert out[0]["content"][0]["text"] == "dawai yaad dilana"


async def test_the_filter_is_emptiness_not_nullness():
    """`is not null` was the original bug. An empty string is not null."""
    conn = Conn({"from messages": []})
    await conversation.history(conn, user_id=15)
    sql = conn.sql[0]
    assert "<> ''" in sql, "history still filters only on null"


# --- the write side ---------------------------------------------------------

@pytest.mark.parametrize("blank", ["", "   "])
async def test_a_captionless_image_is_not_stored_as_an_empty_string(blank):
    """Where row 55 came from: an image arrives with body="".

    Stored as NULL it is invisible to history. Stored as '' it is a live mine
    under that user's next twelve turns.
    """
    conn = Conn()
    await pipeline.log_message(conn, 15, "in", "image",
                               wa_message_id="w1", body=blank)
    stored = conn.params[-1]
    assert not any(isinstance(p, str) and p.strip() == "" for p in stored), \
        f"an empty string reached the insert: {stored!r}"


async def test_real_text_is_still_stored():
    conn = Conn()
    await pipeline.log_message(conn, 15, "in", "text",
                               wa_message_id="w2", body="dawai yaad dilana")
    assert any(p == "dawai yaad dilana" for p in conn.params[-1])
