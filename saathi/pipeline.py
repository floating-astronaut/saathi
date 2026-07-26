"""The inbound path: one WhatsApp message, start to finish.

    webhook -> dedupe -> window touch -> SAFETY -> [audio: fetch/transcode/STT
    -> entity correction] -> agent loop -> WhatsApp-safe text -> send

Ordering here is the product, not an implementation detail:

  * **Safety runs before the model, always.** §12 and risk R7. A forwarded scam
    message is untrusted input that will try to talk its way past a prompt
    instruction; it cannot talk its way past a regex that already returned.
  * **Dedupe before anything with a side effect.** Meta retries webhooks
    aggressively, and a retried reminder-ack must not double-fire.
  * **Window touch before sending.** The inbound message is what reopens the
    24-hour free window; touching it first is what makes the reply free-form
    rather than a template (§11).
  * **STT feeds on memory.** The user's own medicine and people names are the
    bias vocabulary for the correction pass (§10), which is why memory is
    loaded before transcription rather than after.
"""
from __future__ import annotations

import logging

from . import commands, conversation, identity, memory, onboarding, training
from .config import settings
from .agent import loop
from .agent.tools.handlers import Handlers
from .safety.classifier import classify
from .speech import stt as stt_mod
from .speech.audio import ogg_to_wav16k
from .channels import registry
from .wa import window

log = logging.getLogger("saathi.pipeline")


async def already_seen(conn, wa_message_id: str | None) -> bool:
    """Meta retries. A replayed webhook must be a no-op, not a second reminder."""
    if not wa_message_id:
        return False
    row = await (await conn.execute(
        "select 1 from messages where wa_message_id = %s", (wa_message_id,))).fetchone()
    return row is not None


async def log_message(conn, user_id: int, direction: str, kind: str, *,
                      wa_message_id: str | None = None, body: str | None = None,
                      transcript: str | None = None, transcript_raw: str | None = None,
                      stt_ms: int | None = None, template: str | None = None) -> int:
    row = await (await conn.execute(
        """insert into messages (user_id, direction, kind, wa_message_id, body_text,
                                 transcript, transcript_raw, stt_ms, template_name)
           values (%s,%s,%s,%s,%s,%s,%s,%s,%s)
           on conflict (wa_message_id) do nothing
           returning id""",
        (user_id, direction, kind, wa_message_id, body, transcript,
         transcript_raw, stt_ms, template),
    )).fetchone()
    return row[0] if row else 0


async def handle_ack(conn, user_id: int, button_id: str) -> str | None:
    """Quick-reply buttons on a fired reminder: acknowledge or snooze.

    Handled deterministically rather than through the model — an ack is an
    unambiguous button press, and routing it through an LLM would add latency,
    cost, and a chance of getting it wrong.
    """
    if button_id.startswith("ack:"):
        await conn.execute(
            """update reminder_fires set state = 'acked', acked_at = now()
                where id = %s and user_id = %s""",
            (int(button_id.split(":", 1)[1]), user_id))
        return "Shabaash! Ho gaya."
    if button_id.startswith("snooze:"):
        _, fire_id, mins = button_id.split(":", 2)
        await conn.execute(
            """update reminder_fires
                  set state = 'snoozed', snoozed_to = now() + (%s || ' minutes')::interval
                where id = %s and user_id = %s""",
            (mins, int(fire_id), user_id))
        return f"Theek hai, {mins} minute baad yaad dila dungi."
    return None


async def transcribe_voice(conn, user_id: int, media_id: str,
                           channel: str = "whatsapp") -> stt_mod.Transcript:
    """Voice note -> corrected transcript, biased by what we know about the user.

    Media URLs expire in minutes (§9), so the fetch happens immediately and is
    not deferred behind anything slower.
    """
    ogg = await registry.get(channel).fetch_media(media_id)
    wav = await ogg_to_wav16k(ogg)
    entities = await memory.surface_forms(conn, user_id)
    return await stt_mod.transcribe(wav, entities=entities)


async def _contribute_corrections(conn, user_id: int, transcript) -> None:
    """Feed confirmed ASR repairs into the derived corpus.

    Looks up each corrected value's entity kind so that person and place names
    are excluded — a repair on a family member's name is never trainable, however
    useful it would be. Failures here must never affect the user's turn.
    """
    for c in transcript.corrections:
        try:
            row = await (await conn.execute(
                """select kind::text from facts
                    where user_id = %s and deleted_at is null
                      and (value ilike %s or %s = any(surface_forms))
                    limit 1""",
                (user_id, f"%{c.replacement}%", c.replacement))).fetchone()
            if row:
                await training.record_correction(conn, user_id,
                                                 c.original, c.replacement, row[0])
        except Exception:  # noqa: BLE001 - training must never break a reply
            log.exception("training contribution failed")


async def _onboarding_state(conn, user_id: int) -> str:
    row = await (await conn.execute(
        "select onboarding::text from users where id = %s", (user_id,))).fetchone()
    return row[0] if row else "new"


HELP_TEXT = (
    "Main yeh kar sakti hoon:\n"
    "• Reminder lagana — \"roz subah aath baje dawa\"\n"
    "• Cheezein yaad rakhna — \"mere doctor Dr Sharma hain\"\n"
    "• Sawaal ka jawab dena, message samjhana\n"
    "• Saamaan ki list banana\n\n"
    "Kabhi bhi keh sakte hain: \"mere baare mein kya jaante ho\", "
    "\"sab kuch bhool jao\", ya \"band karo\"."
)


async def _run_command(conn, transport, user_id: int, handle: str, cmd) -> dict | None:
    """Deterministic handling of unambiguous requests. No model, no cost."""
    from .agent.tools.handlers import Handlers
    C = commands.Command
    if cmd is C.HELP:
        await transport.send_text(conn, user_id, handle, HELP_TEXT)
        return {}
    if cmd is C.STOP:
        await conn.execute("update users set paused = true where id = %s", (user_id,))
        await transport.send_text(conn, user_id, handle,
            "Theek hai, main ab message nahi bhejungi. 'chalu karo' kehkar wapas "
            "shuru kar sakte hain.\n\nStopped. Say \"resume\" to start again.")
        return {}
    if cmd is C.RESUME:
        await conn.execute("update users set paused = false where id = %s", (user_id,))
        await transport.send_text(conn, user_id, handle, "Wapas shuru! / Resumed.")
        return {}
    if cmd is C.WHAT_YOU_KNOW:
        known = await memory.describe(conn, user_id)
        if not known["count"]:
            body = "Abhi mere paas aapke baare mein kuch bhi nahi hai.\n\nI have nothing stored about you yet."
        else:
            lines = [f"• {v}" for vals in known["known"].values() for v in vals]
            body = ("Mere paas yeh hai:\n" + "\n".join(lines) +
                    "\n\nKuch hatana ho to bataiye.")
        await transport.send_text(conn, user_id, handle, body)
        return {}
    if cmd is C.CLEAR_CHAT:
        n = await conversation.clear_conversation(conn, user_id)
        await transport.send_text(conn, user_id, handle,
            f"Chat saaf kar di ({n} message). Aapke reminders aur yaadein waise hi hain.\n\n"
            f"Chat cleared. Your reminders and memories are untouched.")
        return {}
    if cmd is C.DELETE_ALL:
        # Confirm once — it cannot be undone. The confirmation is a button so
        # there is no ambiguity about what "yes" meant.
        await transport.send_buttons(conn, user_id, handle,
            "Kya aap sach mein sab kuch hataana chahte hain? Yeh wapas nahi aayega.\n\n"
            "Delete everything? This cannot be undone.",
            [("del:yes", "Haan, sab hatao"), ("del:no", "Nahi, rehne do")])
        return {}
    if cmd is C.START:
        return None      # a bare greeting from an onboarded user is conversation
    return None


async def handle_message(conn, msg: dict, contact_name: str | None = None,
                         channel: str = "whatsapp") -> dict:
    """Process one inbound message on any channel.

    Channel-agnostic by construction: the only channel-specific things reached
    from here are the transport (how to send) and the session window (whether a
    free-form send is currently legal). Everything else — identity, safety,
    memory, the agent — is shared, which is what lets Telegram be additive.
    """
    transport = registry.get(channel)
    handle = msg.get("from")
    wa_mid = msg.get("id")
    kind = msg.get("type", "text")

    who = await identity.resolve(conn, channel, handle, contact_name,
                                 dm_policy=settings.saathi_dm_policy)
    ob_state = await _onboarding_state(conn, who.user_id)
    user_id, tz, voice_pref = who.user_id, who.tz, who.voice_reply_pref
    display_name = who.display_name

    if await already_seen(conn, wa_mid):
        log.info("duplicate webhook for %s, ignoring", wa_mid)
        return {"skipped": "duplicate"}

    # --- ADMISSION -----------------------------------------------------------
    # Under `pairing` an unknown handle is refused outright. Under `open` (the
    # default now that onboarding exists) anyone may start, which is safe because
    # onboarding below never calls the model.
    if who.status == "pending" and settings.saathi_dm_policy == "pairing":
        if await identity.should_explain(conn, who.user_channel_id,
                                         settings.saathi_admission_max_replies):
            await transport.send_text(conn, who.user_id, handle, identity.ADMISSION_REPLY)
        log.info("unadmitted handle %s/%s — not processed", channel, handle)
        return {"skipped": "not_admitted"}

    # The session window is a WhatsApp concept; channels without one skip it.
    if transport.capabilities.has_session_window:
        await window.touch(conn, user_id)
    convo_id = await conversation.current(conn, user_id, channel)

    # --- interactive button: deterministic, never reaches the model ---------
    if kind == "interactive":
        btn = ((msg.get("interactive") or {}).get("button_reply") or {}).get("id", "")
        ob = await onboarding.handle_button(conn, transport, user_id, handle,
                                            btn, display_name)
        if ob is not None:
            await log_message(conn, user_id, "in", "interactive",
                              wa_message_id=wa_mid, body=btn)
            return {"handled": "onboarding", **ob}
        if btn.startswith("del:"):
            if btn == "del:yes":
                await memory.erase(conn, user_id, hard=True)
                await identity.revoke(conn, channel, handle, "user erasure")
                await transport.send_text(conn, user_id, handle,
                    "Sab kuch hata diya gaya. Alvida, aur khayal rakhiyega. 🌼\n\n"
                    "Everything has been deleted. Take care.")
                return {"handled": "erased"}
            await transport.send_text(conn, user_id, handle,
                "Theek hai, kuch nahi hataaya. / Nothing was deleted.")
            return {"handled": "erase_cancelled"}
        reply = await handle_ack(conn, user_id, btn)
        await log_message(conn, user_id, "in", "interactive", wa_message_id=wa_mid, body=btn)
        if reply:
            await transport.send_text(conn, user_id, handle, reply)
            await log_message(conn, user_id, "out", "text", body=reply)
            return {"handled": "ack", "button": btn}

    # --- get the text, transcribing if it arrived as voice -----------------
    transcript = None
    if kind == "audio":
        media_id = (msg.get("audio") or {}).get("id")
        transcript = await transcribe_voice(conn, user_id, media_id, channel)
        text = transcript.text
        voice_in = True
    else:
        text = (msg.get("text") or {}).get("body", "") or ""
        voice_in = False

    # The correction pass already produced gold-labelled pairs; contributing
    # them is opt-in and gated per-entity inside training.record_correction.
    if transcript and transcript.corrections:
        await _contribute_corrections(conn, user_id, transcript)

    msg_id = await log_message(
        conn, user_id, "in", kind, wa_message_id=wa_mid, body=text,
        transcript=transcript.text if transcript else None,
        transcript_raw=transcript.raw if transcript else None,
        stt_ms=transcript.ms if transcript else None)

    # --- ONBOARDING: deterministic, no model call ---------------------------
    # Safety still runs first (below) for anyone already onboarded, but a brand
    # new sender must be greeted before anything else — including before we spend
    # a model turn deciding what they meant.
    if ob_state == "new":
        await onboarding.begin(conn, transport, user_id, handle)
        return {"handled": "onboarding", "onboarding": "welcome"}

    # --- SAFETY: before the model sees anything (§12, R7) -------------------
    verdict = classify(text)
    if verdict.blocks_llm:
        await conn.execute(
            """insert into safety_events (user_id, message_id, trigger, matched, action)
               values (%s,%s,%s,%s,'blocked_llm')""",
            (user_id, msg_id or None, verdict.trigger.value, verdict.matched))
        await transport.send_text(conn, user_id, handle, verdict.reply)
        await log_message(conn, user_id, "out", "text", body=verdict.reply)
        log.warning("safety trigger %s for user %s", verdict.trigger.value, user_id)
        return {"handled": "safety", "trigger": verdict.trigger.value}

    if not text.strip():
        return {"skipped": "empty"}

    # Mid-onboarding free text (the name step). Still no model call.
    if ob_state not in ("done",):
        ob = await onboarding.handle_text(conn, transport, user_id, handle, ob_state, text)
        if ob is not None:
            return {"handled": "onboarding", **ob}

    # --- INLINE COMMANDS: unambiguous, deterministic, work when the model is
    # down. A DPDP erasure request must not depend on Bedrock being up.
    cmd = commands.parse(text)
    if cmd.command:
        out = await _run_command(conn, transport, user_id, handle, cmd.command)
        if out is not None:
            return {"handled": "command", "command": cmd.command.value, **out}

    # --- agent -------------------------------------------------------------
    facts = await memory.load_facts(conn, user_id)
    prior = await conversation.history(conn, user_id)
    turn = await loop.run(text, facts, Handlers(conn, user_id, tz).handle,
                          history=prior, user_name=display_name)
    await conversation.touch(conn, convo_id)
    # R6: is this a task or just conversation? Instrument from day one.
    await loop.record(conn, turn, user_id, msg_id or None,
                      turn_kind="task" if turn.tool_calls else "chat")

    reply = transport.format_text(turn.text) or "Maaf kijiye, main samajh nahi payi. Phir se boliye?"
    await transport.send_text(conn, user_id, handle, reply)
    await log_message(conn, user_id, "out", "text", body=reply)

    return {"handled": "agent", "channel": channel, "voice_in": voice_in,
            "tools": [n for n, _ in turn.tool_calls],
            "reply": reply, "prefix_tokens": turn.prefix_tokens}


def extract_messages(payload: dict) -> list[tuple[dict, str | None]]:
    """Pull (message, contact_name) pairs out of a Cloud API webhook envelope.

    The envelope nests four levels deep and every level is a list, so this is
    written defensively — a malformed payload should yield nothing rather than
    raise inside the request handler.
    """
    out: list[tuple[dict, str | None]] = []
    for entry in payload.get("entry", []) or []:
        for change in entry.get("changes", []) or []:
            value = change.get("value") or {}
            names = {c.get("wa_id"): (c.get("profile") or {}).get("name")
                     for c in value.get("contacts", []) or []}
            for m in value.get("messages", []) or []:
                out.append((m, names.get(m.get("from"))))
    return out
