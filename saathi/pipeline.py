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

from . import memory
from .agent import loop
from .agent.tools.handlers import Handlers
from .safety.classifier import classify
from .speech import stt as stt_mod
from .speech.audio import ogg_to_wav16k
from .wa import client as wa
from .wa import window
from .wa.format import to_whatsapp_text

log = logging.getLogger("saathi.pipeline")


async def upsert_user(conn, wa_id: str, name: str | None) -> tuple[int, str, str, str | None]:
    """Return (user_id, tz, voice_reply_pref, display_name); creates on first contact."""
    row = await (await conn.execute(
        """insert into users (wa_id, display_name) values (%s, %s)
           on conflict (wa_id) do update
              set display_name = coalesce(excluded.display_name, users.display_name)
           returning id, tz, voice_reply_pref, display_name""",
        (wa_id, name),
    )).fetchone()
    return row[0], row[1], row[2], row[3]


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


async def transcribe_voice(conn, user_id: int, media_id: str) -> stt_mod.Transcript:
    """Voice note -> corrected transcript, biased by what we know about the user.

    Media URLs expire in minutes (§9), so the fetch happens immediately and is
    not deferred behind anything slower.
    """
    ogg = await wa.fetch_media(media_id)
    wav = await ogg_to_wav16k(ogg)
    entities = await memory.surface_forms(conn, user_id)
    return await stt_mod.transcribe(wav, entities=entities)


async def handle_message(conn, msg: dict, contact_name: str | None = None) -> dict:
    """Process one inbound message. Returns a small dict for logging/tests."""
    wa_id = msg.get("from")
    wa_mid = msg.get("id")
    kind = msg.get("type", "text")

    user_id, tz, voice_pref, display_name = await upsert_user(conn, wa_id, contact_name)

    if await already_seen(conn, wa_mid):
        log.info("duplicate webhook for %s, ignoring", wa_mid)
        return {"skipped": "duplicate"}

    await window.touch(conn, user_id)

    # --- interactive button: deterministic, never reaches the model ---------
    if kind == "interactive":
        btn = ((msg.get("interactive") or {}).get("button_reply") or {}).get("id", "")
        reply = await handle_ack(conn, user_id, btn)
        await log_message(conn, user_id, "in", "interactive", wa_message_id=wa_mid, body=btn)
        if reply:
            await wa.send_text(conn, user_id, wa_id, reply)
            await log_message(conn, user_id, "out", "text", body=reply)
            return {"handled": "ack", "button": btn}

    # --- get the text, transcribing if it arrived as voice -----------------
    transcript = None
    if kind == "audio":
        media_id = (msg.get("audio") or {}).get("id")
        transcript = await transcribe_voice(conn, user_id, media_id)
        text = transcript.text
        voice_in = True
    else:
        text = (msg.get("text") or {}).get("body", "") or ""
        voice_in = False

    msg_id = await log_message(
        conn, user_id, "in", kind, wa_message_id=wa_mid, body=text,
        transcript=transcript.text if transcript else None,
        transcript_raw=transcript.raw if transcript else None,
        stt_ms=transcript.ms if transcript else None)

    # --- SAFETY: before the model sees anything (§12, R7) -------------------
    verdict = classify(text)
    if verdict.blocks_llm:
        await conn.execute(
            """insert into safety_events (user_id, message_id, trigger, matched, action)
               values (%s,%s,%s,%s,'blocked_llm')""",
            (user_id, msg_id or None, verdict.trigger.value, verdict.matched))
        await wa.send_text(conn, user_id, wa_id, verdict.reply)
        await log_message(conn, user_id, "out", "text", body=verdict.reply)
        log.warning("safety trigger %s for user %s", verdict.trigger.value, user_id)
        return {"handled": "safety", "trigger": verdict.trigger.value}

    if not text.strip():
        return {"skipped": "empty"}

    # --- agent -------------------------------------------------------------
    facts = await memory.load_facts(conn, user_id)
    turn = await loop.run(text, facts, Handlers(conn, user_id, tz).handle,
                          user_name=display_name)
    # R6: is this a task or just conversation? Instrument from day one.
    await loop.record(conn, turn, user_id, msg_id or None,
                      turn_kind="task" if turn.tool_calls else "chat")

    reply = to_whatsapp_text(turn.text) or "Maaf kijiye, main samajh nahi payi. Phir se boliye?"
    await wa.send_text(conn, user_id, wa_id, reply)
    await log_message(conn, user_id, "out", "text", body=reply)

    return {"handled": "agent", "voice_in": voice_in,
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
