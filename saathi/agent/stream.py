"""Streaming turns via Bedrock ConverseStream.

WhatsApp cannot render a message that grows -- there is no token-by-token
display to feed. So streaming buys us two specific things, both of which
matter for a voice-first elder:

  1. **Time to first sentence.** We can send (or start speaking) sentence one
     while the rest is still generating. On a 3-4 second reply that is the
     difference between "it's thinking" and "it's stuck".
  2. **Earlier TTS.** Synthesis is per-utterance; starting it on the first
     complete sentence overlaps synthesis with generation instead of queuing
     them. PRD s9 structures phrases as separate sentences anyway, so the
     sentence boundary is already the natural unit.

Tool use complicates streaming: the model emits toolUse input as a series of
partial-JSON deltas, which must be accumulated and only parsed once the block
closes. That is handled here rather than pushed onto callers.
"""
from __future__ import annotations

import json
import logging
import re
import time
from typing import AsyncIterator

import boto3

from ..config import settings
from .prompt import build_prefix
from .tools.specs import TOOL_CONFIG

log = logging.getLogger("saathi.agent.stream")

# Split on sentence enders, keeping Devanagari danda. Deliberately conservative:
# a wrongly-split sentence sounds worse in TTS than a slightly late one.
_SENTENCE_END = re.compile(r"(?<=[.!?।])\s+")

_client = None


def client():
    global _client
    if _client is None:
        _client = boto3.client("bedrock-runtime", region_name=settings.bedrock_region)
    return _client


class StreamedTurn:
    """Accumulates everything a streamed turn produced."""

    def __init__(self) -> None:
        self.text = ""
        self.tool_calls: list[tuple[str, dict]] = []
        self.input_tokens = 0
        self.output_tokens = 0
        self.prefix_tokens = 0
        self.latency_ms = 0
        self.first_sentence_ms: int | None = None


async def stream_turn(
    user_text: str,
    facts: list[tuple[str, str]],
    history: list[dict] | None = None,
) -> AsyncIterator[tuple[str, object]]:
    """Yield ('sentence', str) as sentences complete, then ('done', StreamedTurn).

    Also yields ('tool', (name, args)) when the model asks for a tool, so the
    caller can execute it. Callers that do not care about incremental output
    can simply drain to the final ('done', ...).
    """
    prefix = build_prefix(facts, 0, settings.saathi_prefix_token_budget)
    messages = list(history or [])
    messages.append({"role": "user", "content": [{"text": user_text}]})

    turn = StreamedTurn()
    turn.prefix_tokens = prefix.tokens
    started = time.monotonic()

    resp = client().converse_stream(
        modelId=settings.saathi_model_id,
        system=[{"text": prefix.system}],
        messages=messages,
        toolConfig=TOOL_CONFIG,
        inferenceConfig={"maxTokens": 700, "temperature": 0.2},
    )

    buffer = ""
    tool_name: str | None = None
    tool_json = ""

    for event in resp["stream"]:
        if "contentBlockStart" in event:
            start = event["contentBlockStart"].get("start", {})
            if "toolUse" in start:
                tool_name = start["toolUse"]["name"]
                tool_json = ""

        elif "contentBlockDelta" in event:
            delta = event["contentBlockDelta"]["delta"]
            if "text" in delta:
                buffer += delta["text"]
                turn.text += delta["text"]
                # emit complete sentences as they form
                parts = _SENTENCE_END.split(buffer)
                if len(parts) > 1:
                    for sentence in parts[:-1]:
                        s = sentence.strip()
                        if s:
                            if turn.first_sentence_ms is None:
                                turn.first_sentence_ms = int((time.monotonic() - started) * 1000)
                            yield ("sentence", s)
                    buffer = parts[-1]
            elif "toolUse" in delta:
                tool_json += delta["toolUse"].get("input", "")

        elif "contentBlockStop" in event:
            if tool_name is not None:
                try:
                    args = json.loads(tool_json) if tool_json.strip() else {}
                except json.JSONDecodeError:
                    log.warning("tool %s: unparseable streamed input %r", tool_name, tool_json[:120])
                    args = {}
                turn.tool_calls.append((tool_name, args))
                yield ("tool", (tool_name, args))
                tool_name, tool_json = None, ""

        elif "metadata" in event:
            usage = event["metadata"].get("usage", {})
            turn.input_tokens += usage.get("inputTokens", 0)
            turn.output_tokens += usage.get("outputTokens", 0)

    tail = buffer.strip()
    if tail:
        if turn.first_sentence_ms is None:
            turn.first_sentence_ms = int((time.monotonic() - started) * 1000)
        yield ("sentence", tail)

    turn.latency_ms = int((time.monotonic() - started) * 1000)
    yield ("done", turn)
