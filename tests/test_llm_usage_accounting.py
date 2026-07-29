"""Slice-B accounting must observe each model request without affecting replies."""
import asyncio

from saathi.agent import loop
from saathi import openrouter


class Bedrock:
    def converse(self, **_kw):
        return {"ResponseMetadata": {"RequestId": "bedrock-1"},
                "usage": {"inputTokens": 4, "outputTokens": 2},
                "output": {"message": {"role": "assistant", "content": [{"text": "ok"}]}}}


async def no_tools(*_args):
    raise AssertionError("no tool expected")


async def test_bedrock_request_is_observed_once_with_actual_usage(monkeypatch):
    monkeypatch.setattr(loop, "_client", Bedrock())
    events = []
    async def recorder(resp, vendor, latency_ms, hop):
        events.append((resp, vendor, latency_ms, hop))
    turn = await loop.run("hello", [], no_tools, usage_recorder=recorder)
    assert turn.text == "ok"
    assert len(events) == 1
    assert events[0][1:] and events[0][1] == "bedrock"
    assert events[0][0]["usage"] == {"inputTokens": 4, "outputTokens": 2}


async def test_openrouter_request_is_observed_once(monkeypatch):
    async def converse(*_args, **_kwargs):
        return {"request_id": "or-1", "reported_cost": 0.001,
                "usage": {"inputTokens": 5, "outputTokens": 3},
                "output": {"message": {"role": "assistant", "content": [{"text": "ok"}]}}}
    monkeypatch.setattr(openrouter, "converse", converse)
    vendors = []
    async def recorder(_resp, vendor, _latency_ms, _hop): vendors.append(vendor)
    await loop.run("hello", [], no_tools, ai_api_key="not-a-real-key", usage_recorder=recorder)
    assert vendors == ["openrouter"]


async def test_observer_failure_does_not_break_a_successful_reply(monkeypatch):
    monkeypatch.setattr(loop, "_client", Bedrock())
    async def broken(*_args): raise RuntimeError("ledger unavailable")
    turn = await loop.run("hello", [], no_tools, usage_recorder=broken)
    assert turn.text == "ok"


def test_openrouter_normalizer_keeps_request_id_and_reported_cost():
    out = openrouter._bedrockish_response({"id": "gen-1", "choices": [{"message": {}}],
                                            "usage": {"prompt_tokens": 2,
                                                      "completion_tokens": 1, "cost": 0.003}})
    assert out["request_id"] == "gen-1"
    assert out["reported_cost"] == 0.003
