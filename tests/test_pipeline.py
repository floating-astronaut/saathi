"""Inbound pipeline. The ordering guarantees are the product, so they're tested
as behaviour rather than trusted to code review."""
import pytest
from saathi.pipeline import extract_messages


def _env(msgs, contacts=None):
    return {"entry": [{"changes": [{"value": {
        "contacts": contacts or [], "messages": msgs}}]}]}


def test_extracts_text_message_with_contact_name():
    got = extract_messages(_env(
        [{"id": "wamid.1", "from": "919812345678", "type": "text", "text": {"body": "namaste"}}],
        [{"wa_id": "919812345678", "profile": {"name": "Kamala"}}]))
    assert len(got) == 1
    msg, name = got[0]
    assert msg["id"] == "wamid.1" and name == "Kamala"


def test_extracts_multiple_messages_across_entries():
    payload = {"entry": [
        {"changes": [{"value": {"messages": [{"id": "a", "from": "1", "type": "text"}]}}]},
        {"changes": [{"value": {"messages": [{"id": "b", "from": "2", "type": "audio"}]}}]},
    ]}
    assert [m["id"] for m, _ in extract_messages(payload)] == ["a", "b"]


@pytest.mark.parametrize("payload", [
    {}, {"entry": []}, {"entry": [{}]}, {"entry": [{"changes": [{}]}]},
    {"entry": [{"changes": [{"value": {}}]}]},
    {"entry": [{"changes": [{"value": {"messages": None}}]}]},
    # a status callback carries no messages at all — must not raise
    {"entry": [{"changes": [{"value": {"statuses": [{"status": "delivered"}]}}]}]},
])
def test_malformed_or_statusonly_payloads_yield_nothing(payload):
    assert extract_messages(payload) == []


def test_unknown_contact_name_is_none_not_crash():
    got = extract_messages(_env([{"id": "x", "from": "999", "type": "text"}]))
    assert got[0][1] is None
