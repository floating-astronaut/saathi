"""Every outbound message must land in `messages`.

Written because the first real user received five messages and none were
recorded. Onboarding calls the transport directly, and only `pipeline` and the
reminder worker remembered to insert afterwards — so the consent text a user was
shown was missing from the table the backups protect, while `consent_at` said
they had agreed to it.

The fix records at the single wire path. These pin that it stays there, and that
it never takes a send down with it.
"""
import logging

from saathi.wa import client


class Cur:
    async def fetchone(self): return None
    async def fetchall(self): return []


class Conn:
    def __init__(self, boom=False):
        self.sql: list[str] = []
        self.params: list[tuple] = []
        self.boom = boom
    async def execute(self, q, params=None):
        if self.boom:
            raise RuntimeError("database is having a day")
        self.sql.append(" ".join(q.split()))
        self.params.append(params)
        return Cur()

    def recorded(self):
        for q, p in zip(self.sql, self.params):
            if "insert into messages" in q:
                return p
        return None


# --- payload -> row shape ----------------------------------------------------

def test_text_is_described_as_text():
    assert client._describe(
        {"type": "text", "text": {"body": "Namaste"}}) == ("text", "Namaste", None)


def test_interactive_body_is_captured():
    """Onboarding sends buttons; the body is the consent text we must retain."""
    kind, body, tpl = client._describe(
        {"type": "interactive",
         "interactive": {"body": {"text": "Shuru karein?"}}})
    assert (kind, body, tpl) == ("interactive", "Shuru karein?", None)


def test_template_keeps_name_and_the_variables_the_user_read():
    kind, body, tpl = client._describe({
        "type": "template",
        "template": {"name": "reminder_fire_v2",
                     "components": [{"type": "body", "parameters": [
                         {"type": "text", "text": "BP ki dawai"}]}]}})
    assert kind == "template" and tpl == "reminder_fire_v2"
    assert body == "BP ki dawai"


def test_unknown_type_still_records_rather_than_vanishing():
    kind, _, _ = client._describe({"type": "sticker"})
    assert kind == "text"


# --- the record itself -------------------------------------------------------

async def test_outbound_is_recorded_with_direction_out():
    conn = Conn()
    await client._record_outbound(conn, 7, "wamid.X", {"type": "text", "text": {"body": "hi"}})
    p = conn.recorded()
    assert p is not None, "outbound message was not recorded"
    assert p[0] == 7 and p[2] == "wamid.X" and p[3] == "hi"


async def test_record_is_idempotent_on_message_id():
    """pipeline still inserts too; the unique index must absorb it."""
    conn = Conn()
    await client._record_outbound(conn, 7, "wamid.X", {"type": "text", "text": {"body": "hi"}})
    assert "on conflict (wa_message_id) do nothing" in conn.sql[0]


async def test_a_failed_record_never_breaks_the_send(caplog):
    """The message has already gone out. Raising would invite a resend."""
    conn = Conn(boom=True)
    with caplog.at_level(logging.ERROR, logger="saathi.wa"):
        await client._record_outbound(conn, 7, "wamid.X", {"type": "text", "text": {"body": "hi"}})
    assert any(r.levelno >= logging.ERROR for r in caplog.records)


# --- the wire path must actually call it -------------------------------------

async def test_send_records_without_being_asked(monkeypatch):
    """The one that matters. Tests above exercise _record_outbound directly, so
    deleting the call from _send would leave them all green. This fails if the
    wire path stops recording."""
    conn = Conn()
    sent = {}

    class Resp:
        status_code = 200
        text = ""
        def raise_for_status(self): pass
        def json(self): return {"messages": [{"id": "wamid.WIRE"}]}

    class HTTP:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, url, headers=None, json=None):
            sent["payload"] = json
            return Resp()

    monkeypatch.setattr(client.httpx, "AsyncClient", lambda **kw: HTTP())
    async def _ok(*a, **k): return None
    monkeypatch.setattr(client, "assert_can_send", _ok)

    mid = await client._send(conn, 7, "+911", {"type": "text", "text": {"body": "hi"}},
                             client.Channel.FREEFORM)
    assert mid == "wamid.WIRE"
    p = conn.recorded()
    assert p is not None, "_send did not record the outbound message"
    assert p[2] == "wamid.WIRE"
