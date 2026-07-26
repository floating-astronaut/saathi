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

from . import (commands, conversation, documents, identity, memory,
               onboarding, training, vision)
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


async def _handle_media(conn, transport, user_id: int, handle: str,
                        msg: dict, kind: str, wa_mid: str | None) -> dict | None:
    """Read an image or document and reply with what it says.

    Deliberately does not go through the agent loop: the vision model *is* the
    answer, and routing its output back through a text model would add latency,
    cost, and a chance of the disclaimer being paraphrased away.
    """
    node = msg.get(kind) or {}
    media_id = node.get("id")
    caption = (node.get("caption") or "").strip() or None
    mime = node.get("mime_type")
    if not media_id:
        return None
    try:
        blob = await transport.fetch_media(media_id)
    except Exception:  # noqa: BLE001
        log.exception("media fetch failed")
        await transport.send_text(conn, user_id, handle,
            "Maaf kijiye, yeh file main khol nahi payi. Dobara bhej sakte hain?\n\n"
            "Sorry, I couldn't open that. Could you send it again?")
        return {"handled": "media_error"}

    reading = None
    if kind == "document" and "pdf" in (mime or "").lower():
        text = documents.extract_text(blob)
        if documents.has_text_layer(text):
            reading = await _read_pdf_text(text, caption)
        else:
            page = await documents.render_first_page(blob)
            if page:
                reading = await vision.read_document(page, "image/png", caption)
    if reading is None:
        intent = vision.classify_intent(caption)
        if intent == "medicine":
            reading = await vision.describe_medicine(blob, mime)
        elif intent == "document":
            reading = await vision.read_document(blob, mime, caption)
        else:
            reading = await vision.describe_image(blob, mime, caption)

    body = transport.format_text(reading.rendered())
    await log_message(conn, user_id, "in", "image" if kind == "image" else "text",
                      wa_message_id=wa_mid, body=caption or f"[{kind}]")
    await transport.send_text(conn, user_id, handle, body)
    await log_message(conn, user_id, "out", "text", body=body)
    return {"handled": "media", "kind": reading.kind, "had_disclaimer": bool(reading.disclaimer)}


async def _read_pdf_text(text: str, question: str | None) -> "vision.Reading":
    """Summarise an extracted text layer with the ordinary text model."""
    from .agent import loop as agent_loop
    ask = question or "What does this say?"
    prompt = (
        "An older adult in India forwarded this document and asks: "
        f"{ask!r}\n\nDocument text:\n" + text[:6000] +
        "\n\nExplain in simple Hinglish, short lines. Lead with what it is and "
        "what they need to do, then any date or amount. If it asks for money, an "
        "OTP, a PIN or bank details, say clearly it looks like a scam."
    )
    turn = await agent_loop.run(prompt, [], _no_tools)
    low = (turn.text or "").lower()
    money = any(w in low for w in ("otp", "pin", "bank", "upi", "payment"))
    return vision.Reading(turn.text or "",
                          vision.MONEY_DISCLAIMER if money else vision.DOCUMENT_DISCLAIMER,
                          "document")


async def _no_tools(name: str, args: dict) -> dict:
    return {"error": "no tools available while reading a document"}


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
    """Assemble the context, then let the capability chain decide.

    This function used to be an if/elif ladder that grew a branch per feature —
    the shape that stops being reviewable at about six capabilities and makes
    ordering implicit. It now does only what genuinely must happen for *every*
    message, in a fixed order, and hands off:

        identity -> admission -> dedupe -> window -> conversation -> transcribe
        -> log -> dispatch

    Adding a capability is a `register(...)` in capabilities.py. It is not an
    edit here.
    """
    from . import capabilities  # noqa: F401 - registers the chain on import
    from .core.context import MessageContext
    from .core.handlers import dispatch

    transport = registry.get(channel)
    handle = msg.get("from")
    wa_mid = msg.get("id")
    kind = msg.get("type", "text")

    who = await identity.resolve(conn, channel, handle, contact_name,
                                 dm_policy=settings.saathi_dm_policy)

    # Admission: under `pairing` an unknown handle never reaches the chain.
    if who.status == "pending" and settings.saathi_dm_policy == "pairing":
        if await identity.should_explain(conn, who.user_channel_id,
                                         settings.saathi_admission_max_replies):
            await transport.send_text(conn, who.user_id, handle, identity.ADMISSION_REPLY)
        log.info("unadmitted handle %s/%s — not processed", channel, handle)
        return {"skipped": "not_admitted"}

    if await already_seen(conn, wa_mid):
        log.info("duplicate webhook for %s, ignoring", wa_mid)
        return {"skipped": "duplicate"}

    if transport.capabilities.has_session_window:
        await window.touch(conn, who.user_id)
    convo_id = await conversation.current(conn, who.user_id, channel)

    ctx = MessageContext(
        conn=conn, transport=transport, channel=channel, handle=handle, msg=msg,
        user_id=who.user_id, display_name=who.display_name, tz=who.tz,
        voice_pref=who.voice_reply_pref,
        onboarding=await _onboarding_state(conn, who.user_id),
        wa_message_id=wa_mid, kind=kind, conversation_id=convo_id,
    )

    # Resolve text once, so every handler sees the same thing whether the user
    # typed it or spoke it.
    if kind == "audio":
        media_id = (msg.get("audio") or {}).get("id")
        ctx.transcript = await transcribe_voice(conn, who.user_id, media_id, channel)
        ctx.text = ctx.transcript.text
        if ctx.transcript.corrections:
            await _contribute_corrections(conn, who.user_id, ctx.transcript)
    elif kind == "interactive":
        ctx.text = ctx.button_id
    else:
        ctx.text = (msg.get("text") or {}).get("body", "") or ""

    if kind != "interactive":
        ctx.message_id = await log_message(
            conn, who.user_id, "in", kind, wa_message_id=wa_mid, body=ctx.text,
            transcript=ctx.transcript.text if ctx.transcript else None,
            transcript_raw=ctx.transcript.raw if ctx.transcript else None,
            stt_ms=ctx.transcript.ms if ctx.transcript else None) or None
    else:
        await log_message(conn, who.user_id, "in", "interactive",
                          wa_message_id=wa_mid, body=ctx.text)

    result = await dispatch(ctx)
    if ctx.meta.get("reply"):
        await log_message(conn, who.user_id, "out", "text", body=ctx.meta["reply"])
    return {"channel": channel, **result}


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
