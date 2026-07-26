"""The agent tool loop, over Bedrock Converse.

Model is `zai.glm-5` on a **regional** ap-south-1 endpoint (no `global.` prefix),
so inference stays in India — see plan §5c. There is no prompt caching on this
model, so the prefix budget in prompt.py is the cost control.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

import boto3

from ..config import settings
from .prompt import Prefix, build_prefix, estimate_tokens
from .tools.specs import TOOL_CONFIG, TOOLS, assert_no_forbidden_tools

log = logging.getLogger("saathi.agent")

MAX_HOPS = 5  # tool round-trips per user turn; elders' tasks are shallow

_client = None


def client():
    global _client
    if _client is None:
        _client = boto3.client("bedrock-runtime", region_name=settings.bedrock_region)
    return _client


def tool_tokens() -> int:
    """Tokens the tool definitions consume — part of the per-turn prefix cost."""
    return estimate_tokens(json.dumps(TOOLS))


@dataclass
class Turn:
    """One user turn and everything it cost."""
    text: str = ""
    tool_calls: list[tuple[str, dict]] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    prefix_tokens: int = 0
    latency_ms: int = 0
    hops: int = 0


ToolHandler = Callable[[str, dict], Awaitable[dict]]


async def run(
    user_text: str,
    facts: list[tuple[str, str]],
    handle_tool: ToolHandler,
    history: list[dict] | None = None,
    user_name: str | None = None,
    allowed_tools: set[str] | None = None,
) -> Turn:
    """Run one user turn to completion, executing tools as the model calls them.

    `handle_tool(name, args) -> dict` performs the side effect and returns a
    JSON-serialisable result. It is the only thing that can change state, which
    keeps the injection surface (PRD §12) to the tool list itself.
    """
    assert_no_forbidden_tools()

    prefix: Prefix = build_prefix(facts, tool_tokens(),
                                  settings.saathi_prefix_token_budget, user_name)
    # Withholding beats filtering: a filter must recognise every phrasing of an
    # attack, while an absent tool does not care what the text says.
    tool_config = TOOL_CONFIG
    if allowed_tools is not None:
        tool_config = {"tools": [t for t in TOOLS
                                 if t["toolSpec"]["name"] in allowed_tools]}
    messages: list[dict] = list(history or [])
    messages.append({"role": "user", "content": [{"text": user_text}]})

    turn = Turn(prefix_tokens=prefix.tokens)
    started = time.monotonic()

    for hop in range(MAX_HOPS):
        turn.hops = hop + 1
        resp = client().converse(
            modelId=settings.saathi_model_id,
            system=[{"text": prefix.system}],
            messages=messages,
            toolConfig=tool_config,
            inferenceConfig={"maxTokens": 700, "temperature": 0.2},
        )
        usage = resp.get("usage", {})
        turn.input_tokens += usage.get("inputTokens", 0)
        turn.output_tokens += usage.get("outputTokens", 0)

        out = resp["output"]["message"]
        messages.append(out)

        uses = [b["toolUse"] for b in out.get("content", []) if "toolUse" in b]
        texts = [b["text"] for b in out.get("content", []) if "text" in b]
        if texts:
            turn.text = "\n".join(t.strip() for t in texts if t.strip())

        if not uses:
            break

        results = []
        for use in uses:
            name, args = use["name"], use.get("input", {})
            turn.tool_calls.append((name, args))
            try:
                payload = await handle_tool(name, args)
                status = "success"
            except Exception as exc:  # noqa: BLE001 - the model gets to see and recover
                log.exception("tool %s failed", name)
                payload, status = {"error": str(exc)[:200]}, "error"
            results.append({"toolResult": {
                "toolUseId": use["toolUseId"],
                "content": [{"json": payload}],
                "status": status,
            }})
        messages.append({"role": "user", "content": results})
    else:
        log.warning("hit MAX_HOPS=%s without settling", MAX_HOPS)

    turn.latency_ms = int((time.monotonic() - started) * 1000)
    return turn


async def record(conn, turn: Turn, user_id: int | None, message_id: int | None,
                 turn_kind: str = "task") -> None:
    """Persist what the turn cost. Without this the prefix budget is unenforceable."""
    await conn.execute(
        """insert into llm_calls
             (user_id, message_id, model, turn_kind, prefix_tokens,
              input_tokens, output_tokens, latency_ms, tool_name)
           values (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (user_id, message_id, settings.saathi_model_id, turn_kind, turn.prefix_tokens,
         turn.input_tokens, turn.output_tokens, turn.latency_ms,
         turn.tool_calls[0][0] if turn.tool_calls else None),
    )


async def run_for_user(conn, user_id: int, user_text: str,
                       history: list[dict] | None = None) -> Turn:
    """Convenience path: load the user's real memory, run, record the cost.

    Keeps callers from having to remember to (a) fetch facts and (b) write the
    llm_calls row — the second is easy to skip and it is what makes the prefix
    budget enforceable.
    """
    from .. import memory
    from .tools.handlers import Handlers

    row = await (await conn.execute(
        "select tz from users where id = %s", (user_id,))).fetchone()
    tz = row[0] if row else "Asia/Kolkata"
    facts = await memory.load_facts(conn, user_id)
    turn = await run(user_text, facts, Handlers(conn, user_id, tz).handle, history)
    await record(conn, turn, user_id, None)
    return turn
