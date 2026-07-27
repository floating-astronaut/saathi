"""The capability chain.

Each capability is registered with a priority rather than wired into a branch,
so adding one is a new block here (or in another module that calls `register`)
and never an edit to the pipeline.

Read top to bottom, this file *is* the specification of what happens to an
inbound message and in what order — which is the property the old if/elif ladder
lost as it grew.
"""
from __future__ import annotations

import logging

from . import (commands, conversation, documents, identity, memory, onboarding,
               provenance as prov, vision)
from .agent import loop as agent_loop
from .agent.tools.handlers import Handlers
from .core.context import MessageContext
from .core.handlers import register, simple
from .safety.classifier import classify

log = logging.getLogger("saathi.capabilities")


# --- 0-9 · safety ------------------------------------------------------------

def _safety_matches(ctx: MessageContext) -> bool:
    return bool(ctx.text.strip()) and classify(ctx.text).blocks_llm


async def _safety_handle(ctx: MessageContext) -> dict:
    v = classify(ctx.text)
    await ctx.conn.execute(
        """insert into safety_events (user_id, message_id, trigger, matched, action)
           values (%s,%s,%s,%s,'blocked_llm')""",
        (ctx.user_id, ctx.message_id, v.trigger.value, v.matched))
    await ctx.reply(v.reply)
    log.warning("safety %s for user %s", v.trigger.value, ctx.user_id)
    return {"handled": "safety", "trigger": v.trigger.value}


register(simple("safety", 0, _safety_matches, _safety_handle))


# --- 10-19 · onboarding ------------------------------------------------------

async def _onboarding_handle(ctx: MessageContext) -> dict | None:
    if ctx.kind == "interactive":
        out = await onboarding.handle_button(
            ctx.conn, ctx.transport, ctx.user_id, ctx.handle,
            ctx.button_id, ctx.display_name)
        return {"handled": "onboarding", **out} if out is not None else None
    if ctx.onboarding == "new":
        await onboarding.begin(ctx.conn, ctx.transport, ctx.user_id, ctx.handle)
        return {"handled": "onboarding", "onboarding": "welcome"}
    out = await onboarding.handle_text(
        ctx.conn, ctx.transport, ctx.user_id, ctx.handle, ctx.onboarding, ctx.text)
    return {"handled": "onboarding", **out} if out is not None else None


register(simple("onboarding", 10,
                lambda c: not c.is_onboarded or c.button_id.startswith("ob:"),
                _onboarding_handle))


# --- 20-29 · deterministic commands -----------------------------------------

async def _erase_buttons(ctx: MessageContext) -> dict:
    if ctx.button_id == "del:yes":
        await memory.erase(ctx.conn, ctx.user_id, hard=True)
        await identity.revoke(ctx.conn, ctx.channel, ctx.handle, "user erasure")
        await ctx.reply("Sab kuch hata diya gaya. Alvida, aur khayal rakhiyega. 🌼\n\n"
                        "Everything has been deleted. Take care.")
        return {"handled": "erased"}
    await ctx.reply("Theek hai, kuch nahi hataaya. / Nothing was deleted.")
    return {"handled": "erase_cancelled"}


register(simple("erase_confirm", 20,
                lambda c: c.button_id.startswith("del:"), _erase_buttons))

register(simple("reminder_ack", 21,
                lambda c: c.button_id.startswith(("ack:", "snooze:")),
                lambda c: _ack(c)))


async def _ack(ctx: MessageContext) -> dict | None:
    from .pipeline import handle_ack
    reply = await handle_ack(ctx.conn, ctx.user_id, ctx.button_id)
    if reply is None:
        return None
    await ctx.reply(reply)
    return {"handled": "ack", "button": ctx.button_id}


# Provenance is checked *here*, in the matcher, not inside the handler — an
# unmatched capability falls through to the agent, which fences relayed text and
# withholds mutating tools. A handler that refused would have to invent its own
# safe behaviour; declining to match reuses the one we already trust.
#
# Why this matters more than it looks: STOP matches `\bunsubscribe\b` as a
# substring, and virtually every forwarded marketing message carries the word in
# its footer. Before this guard, forwarding a promo set `users.paused = true`,
# and `worker/turns._handle` silently declines to send reminders to a paused
# user. A forwarded advert stopped someone's medication reminders indefinitely,
# with no error and — because the ack path is unreachable (PR-4b) — no nudge to
# reveal it.
#
# Priorities 20 and 21 stay unguarded on purpose: they key on `button_id`, and a
# button press is a first-party control the user physically tapped.
#
# Onboarding (10) is deliberately NOT guarded either. It matches on
# `not c.is_onboarded`, and making it provenance-aware would drop an
# un-onboarded user through to the agent — breaking "onboarding never calls the
# model", which is precisely what makes an open door safe.
register(simple("commands", 22,
                lambda c: c.trusted
                          and bool(c.text.strip())
                          and commands.parse(c.text).command is not None,
                lambda c: _command(c)))


async def _command(ctx: MessageContext) -> dict | None:
    from .pipeline import _run_command
    cmd = commands.parse(ctx.text).command
    out = await _run_command(ctx.conn, ctx.transport, ctx.user_id, ctx.handle, cmd)
    return {"handled": "command", "command": cmd.value, **out} if out is not None else None


# --- 30-49 · media -----------------------------------------------------------

async def _media(ctx: MessageContext) -> dict | None:
    from .pipeline import _handle_media
    return await _handle_media(ctx.conn, ctx.transport, ctx.user_id, ctx.handle,
                               ctx.msg, ctx.kind, ctx.wa_message_id)


register(simple("media", 30, lambda c: c.kind in ("image", "document"), _media))


# --- 90-99 · the agent, as the catch-all ------------------------------------

async def _agent(ctx: MessageContext) -> dict:
    facts = await memory.load_facts(ctx.conn, ctx.user_id)
    prior = await conversation.history(ctx.conn, ctx.user_id)
    p = prov.Provenance(ctx.provenance)
    names = {t["toolSpec"]["name"] for t in __import__(
        "saathi.agent.tools.specs", fromlist=["TOOLS"]).TOOLS}
    turn = await agent_loop.run(
        prov.fence(ctx.text, p), facts, Handlers(ctx.conn, ctx.user_id, ctx.tz).handle,
        history=prior, user_name=ctx.display_name,
        allowed_tools=prov.allowed_tools(names, p))
    if ctx.conversation_id:
        await conversation.touch(ctx.conn, ctx.conversation_id)
    await agent_loop.record(ctx.conn, turn, ctx.user_id, ctx.message_id,
                            turn_kind="task" if turn.tool_calls else "chat")
    reply = ctx.transport.format_text(turn.text) or (
        "Maaf kijiye, main samajh nahi payi. Phir se boliye?")
    await ctx.reply(reply)
    ctx.meta["reply"] = reply
    return {"handled": "agent", "tools": [n for n, _ in turn.tool_calls],
            "prefix_tokens": turn.prefix_tokens, "provenance": ctx.provenance}


register(simple("agent", 90, lambda c: bool(c.text.strip()), _agent))
