"""CTWA attribution must be content-free and must never break a turn (CAPI-1).

The load-bearing properties: the event structurally cannot carry message content
or elder PII (the payload has room only for a click id, a name and a time), and a
Graph outage returns cleanly rather than raising into an onboarding completion.
"""
import json
from typing import ClassVar

import pytest

from saathi import capi
from saathi.config import settings


class Cur:
    def __init__(self, row=None): self._row = row
    async def fetchone(self): return self._row


class Conn:
    """Records SQL + params; returns a preset row for the ctwa_clid select."""
    def __init__(self, clid_row=None):
        self.calls = []
        self._clid_row = clid_row
    async def execute(self, q, params=None):
        self.calls.append((" ".join(q.split()), params))
        if "select ctwa_clid" in q.lower():
            return Cur(self._clid_row)
        return Cur(None)


class Resp:
    def __init__(self, status=200, body=None):
        self.status_code = status
        self._body = {"events_received": 1} if body is None else body
        self.text = json.dumps(self._body)
    def json(self): return self._body


class FakeClient:
    """Async-context httpx stand-in. Records the POST; returns or raises as told."""
    last: ClassVar[dict] = {}
    raise_it: ClassVar[bool] = False
    resp: ClassVar[Resp] = Resp()
    def __init__(self, *a, **k): pass
    async def __aenter__(self): return self
    async def __aexit__(self, *a): return False
    async def post(self, url, params=None, json=None):
        FakeClient.last = {"url": url, "params": params, "json": json}
        if FakeClient.raise_it:
            raise RuntimeError("graph is having a day")
        return FakeClient.resp


@pytest.fixture(autouse=True)
def _wire(monkeypatch):
    FakeClient.last = {}
    FakeClient.raise_it = False
    FakeClient.resp = Resp()
    monkeypatch.setattr(capi.httpx, "AsyncClient", FakeClient)
    monkeypatch.setattr(settings, "wa_access_token", "TOKEN")
    monkeypatch.setattr(settings, "wa_business_account_id", "WABA123")
    monkeypatch.setattr(settings, "saathi_capi_test_event_code", "")


# --- capture: write-once, and truly nothing without a referral --------------

async def test_capture_noop_without_referral():
    conn = Conn()
    await capi.capture_referral(conn, 7, {"type": "text", "text": {"body": "hi"}})
    assert conn.calls == []  # the common path never touches the DB


async def test_capture_writes_once_with_clid():
    conn = Conn()
    await capi.capture_referral(conn, 7, {"referral": {"ctwa_clid": "CLID_abc"}})
    assert len(conn.calls) == 1
    sql, params = conn.calls[0]
    assert "update users set ctwa_clid" in sql
    assert "ctwa_clid is null" in sql          # write-once guard is in the SQL
    assert params == ("CLID_abc", 7)


async def test_capture_ignores_malformed_referral():
    conn = Conn()
    await capi.capture_referral(conn, 7, {"referral": {"no_clid": "x"}})
    await capi.capture_referral(conn, 7, {"referral": "not-a-dict"})
    assert conn.calls == []


# --- report: disabled / organic / success / outage --------------------------

async def test_report_noop_when_disabled(monkeypatch):
    monkeypatch.setattr(settings, "saathi_capi_dataset_id", "")
    conn = Conn(clid_row=("CLID",))
    assert await capi.report_lead(conn, 7) is False
    assert conn.calls == []          # returns before touching the DB
    assert FakeClient.last == {}     # and before any HTTP


async def test_report_noop_for_organic_signup(monkeypatch):
    monkeypatch.setattr(settings, "saathi_capi_dataset_id", "DS")
    conn = Conn(clid_row=(None,))    # user has no captured click id
    assert await capi.report_lead(conn, 7) is False
    assert FakeClient.last == {}


async def test_report_sends_and_returns_true(monkeypatch):
    monkeypatch.setattr(settings, "saathi_capi_dataset_id", "DS")
    conn = Conn(clid_row=("CLID_abc",))
    assert await capi.report_lead(conn, 7) is True
    assert FakeClient.last["url"].endswith("/DS/events")
    assert FakeClient.last["params"] == {"access_token": "TOKEN"}


async def test_report_survives_graph_outage(monkeypatch):
    monkeypatch.setattr(settings, "saathi_capi_dataset_id", "DS")
    FakeClient.raise_it = True
    conn = Conn(clid_row=("CLID_abc",))
    assert await capi.report_lead(conn, 7) is False   # did not raise


async def test_report_false_when_not_accepted(monkeypatch):
    monkeypatch.setattr(settings, "saathi_capi_dataset_id", "DS")
    FakeClient.resp = Resp(status=400, body={"error": {"message": "bad"}})
    conn = Conn(clid_row=("CLID_abc",))
    assert await capi.report_lead(conn, 7) is False


# --- the property that matters most: no message content, no elder PII --------

async def test_event_carries_no_content_or_pii(monkeypatch):
    monkeypatch.setattr(settings, "saathi_capi_dataset_id", "DS")
    conn = Conn(clid_row=("CLID_abc",))
    await capi.report_lead(conn, 7)
    event = FakeClient.last["json"]["data"][0]

    # The event's shape has nowhere to put content — assert it exactly.
    assert set(event) == {"event_name", "event_time", "action_source",
                          "messaging_channel", "user_data"}
    assert set(event["user_data"]) == {"ctwa_clid", "whatsapp_business_account_id"}
    assert event["action_source"] == "business_messaging"
    assert event["messaging_channel"] == "whatsapp"
    assert event["user_data"]["ctwa_clid"] == "CLID_abc"
    assert event["user_data"]["whatsapp_business_account_id"] == "WABA123"

    body = json.dumps(FakeClient.last["json"]).lower()
    for leaked in ("transcript", "display_name", "wa_id", "phone", "email", "body_text"):
        assert leaked not in body, f"payload leaked {leaked!r}"


async def test_test_event_code_routes_to_test_tab(monkeypatch):
    monkeypatch.setattr(settings, "saathi_capi_dataset_id", "DS")
    monkeypatch.setattr(settings, "saathi_capi_test_event_code", "TEST123")
    conn = Conn(clid_row=("CLID_abc",))
    await capi.report_lead(conn, 7)
    assert FakeClient.last["json"]["test_event_code"] == "TEST123"
