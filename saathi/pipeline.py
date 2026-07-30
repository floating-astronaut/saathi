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

import io
import logging
import math
import wave

from . import (accounts, capi, commands, conversation, documents, identity,
               memory, media_store, observability, onboarding, privacy,
               provenance, rate_limit, training, usage, vision)
from .config import settings
from .agent import loop
from .agent.tools.handlers import Handlers
from .core import backpressure
from .safety.classifier import classify
from .speech import sarvam_lang
from .speech import stt as stt_mod
from .speech.audio import ogg_to_wav16k
from .channels import registry
from .channels.base import MediaTooLarge
from .wa import window

log = logging.getLogger("saathi.pipeline")


async def already_seen(conn, wa_message_id: str | None) -> bool:
    """Meta retries. A replayed webhook must be a no-op, not a second reminder."""
    if not wa_message_id:
        return False
    row = await (await conn.execute(
        "select 1 from messages where wa_message_id = %s", (wa_message_id,))).fetchone()
    return row is not None


#: The `msg_kind` enum in `db/schema.sql`. WhatsApp's wire types are a longer
#: list than this — `document`, `video`, `sticker`, `location`, `contacts` — and
#: passing one of those straight through is not a bad row, it is an aborted
#: transaction: Postgres answers `invalid input value for enum msg_kind` and the
#: whole turn unwinds.
#:
#: That is what was happening to **every inbound document**. `handle_message`
#: logs before it dispatches, so a forwarded PDF raised here and never reached
#: the media capability at all — which is also why no test caught it: the
#: suite's fake connection records the SQL string and never parses it
#: (`LANDMINES.md`, "a fake connection will certify SQL that Postgres rejects").
MSG_KINDS = frozenset({"text", "audio", "image", "interactive", "template", "system"})


def _msg_kind(kind: str) -> str:
    """Coerce a wire type to the enum, loudly. `text` is the honest fallback:
    the row exists for dedupe and for the transcript, and both survive it."""
    if kind in MSG_KINDS:
        return kind
    log.warning("message kind %r is not in msg_kind; recording it as text", kind)
    return "text"


async def log_message(conn, user_id: int, direction: str, kind: str, *,
                      wa_message_id: str | None = None, body: str | None = None,
                      transcript: str | None = None, transcript_raw: str | None = None,
                      stt_ms: int | None = None, template: str | None = None) -> int:
    # Narrow PII redaction on the write path: the credential never reaches the
    # database rather than being cleaned up later. Names, medicines, places and
    # phone numbers survive — they are the product.
    body = privacy.redact_for_storage(body)
    transcript = privacy.redact_for_storage(transcript)
    transcript_raw = privacy.redact_for_storage(transcript_raw)

    # An image or sticker with no caption arrives here with body="". Stored as
    # an empty string it is *not null*, so it passed `conversation.history`'s
    # filter and became a blank ContentBlock, which Bedrock refuses — breaking
    # every later turn until it aged out of the window. Normalise at the write
    # path so the bad row cannot be created; `history` also filters blanks, for
    # the rows that already exist.
    body = body if (body and body.strip()) else None
    transcript = transcript if (transcript and transcript.strip()) else None
    transcript_raw = transcript_raw if (transcript_raw and transcript_raw.strip()) else None
    row = await (await conn.execute(
        """insert into messages (user_id, direction, kind, wa_message_id, body_text,
                                 transcript, transcript_raw, stt_ms, template_name)
           values (%s,%s,%s,%s,%s,%s,%s,%s,%s)
           on conflict (wa_message_id) do nothing
           returning id""",
        (user_id, direction, _msg_kind(kind), wa_message_id, body, transcript,
         transcript_raw, stt_ms, template),
    )).fetchone()
    return row[0] if row else 0


# gu/ml copy is a first draft pending native review (LANG-2).
ACK_REPLY = {"hi": "शाबाश! हो गया। 🌼", "hi-en": "Shabaash! Ho gaya. 🌼",
             "en": "Lovely — marked as done. 🌼",
             "gu": "શાબાશ! થઈ ગયું. 🌼", "ml": "കൊള്ളാം! ചെയ്തു. 🌼"}
SNOOZE_REPLY = {"hi": "ठीक है, {mins} मिनट बाद याद दिला दूँगी।",
                "hi-en": "Theek hai, {mins} minute baad yaad dila dungi.",
                "en": "Alright, I'll remind you again in {mins} minutes.",
                "gu": "ઠીક છે, {mins} મિનિટ પછી ફરી યાદ કરાવીશ.",
                "ml": "ശരി, {mins} മിനിറ്റിനു ശേഷം വീണ്ടും ഓർമ്മിപ്പിക്കാം."}


async def handle_ack(conn, user_id: int, button_id: str) -> str | None:
    """Quick-reply buttons on a fired reminder: acknowledge or snooze.

    Handled deterministically rather than through the model — an ack is an
    unambiguous button press, and routing it through an LLM would add latency,
    cost, and a chance of getting it wrong.

    The id is a `scheduled_turns.id`. It used to be a `reminder_fires.id`, which
    stopped being written when migration 006 moved dispatch to `scheduled_turns`
    — so the ack updated a row that no longer existed while §15's
    acknowledgement metric read a table nothing fired from (PR-4b).
    """
    from .onboarding import _lang

    if button_id.startswith("ack:"):
        turn_id = int(button_id.split(":", 1)[1])
        await conn.execute(
            """update scheduled_turns set state = 'acked', acked_at = now()
                where id = %s and user_id = %s""", (turn_id, user_id))
        # A reminder that has been acknowledged must not be nudged about.
        await conn.execute(
            """update scheduled_turns set state = 'skipped'
                where kind = 'nudge' and user_id = %s and state = 'pending'
                  and payload->>'origin_turn_id' = %s""",
            (user_id, str(turn_id)))
        return ACK_REPLY.get(await _lang(conn, user_id), ACK_REPLY["hi"])

    if button_id.startswith("snooze:"):
        _, turn_id, mins = button_id.split(":", 2)
        turn_id, mins = int(turn_id), int(mins)
        row = await (await conn.execute(
            """update scheduled_turns
                  set state = 'snoozed', snoozed_to = now() + make_interval(mins => %s)
                where id = %s and user_id = %s
            returning payload, snoozed_to""", (mins, turn_id, user_id))).fetchone()
        # Marking it snoozed is not a reminder. Book the next one, or the user
        # has simply been told "later" by a system that then forgets.
        if row:
            payload, when = row
            from . import scheduling
            await scheduling.enqueue(
                conn, user_id, "reminder", when, payload=payload or {},
                dedupe_key=f"snooze:{turn_id}:{mins}")
        return SNOOZE_REPLY.get(await _lang(conn, user_id),
                                SNOOZE_REPLY["hi"]).format(mins=mins)
    return None


async def transcribe_voice(conn, user_id: int, media_id: str,
                           channel: str = "whatsapp",
                           wa_message_id: str | None = None) -> stt_mod.Transcript:
    """Voice note -> corrected transcript, biased by what we know about the user.

    Media URLs expire in minutes (§9), so the fetch happens immediately and is
    not deferred behind anything slower.
    """
    ogg = await registry.get(channel).fetch_media(media_id, settings.saathi_max_audio_bytes)
    # Keep the original OGG, not the transcode — debugging a mis-hearing needs
    # what the user actually sent.
    await media_store.put_voice(conn, user_id, ogg, wa_message_id=wa_message_id)
    wav = await ogg_to_wav16k(ogg)
    with wave.open(io.BytesIO(wav), "rb") as audio:
        seconds = audio.getnframes() / audio.getframerate()
    rounded_seconds = math.ceil(seconds)
    estimated_paise = usage.sarvam_stt_cost_paise(rounded_seconds)
    row = await (await conn.execute("select account_id from users where id = %s",
                                    (user_id,))).fetchone()
    account_id = row[0] if row else None
    reservation = None

    if usage.enforcement_enabled(
            enabled=settings.saathi_usage_enforcement_enabled,
            mode=settings.saathi_usage_ledger_mode,
            account_cap_paise=settings.saathi_usage_account_cap_paise):
        if account_id is None or not wa_message_id:
            raise usage.UsageAccountingUnavailable("STT accounting lacks account or idempotency key")
        reservation = await usage.reserve(
            conn, idempotency_key=f"stt:{wa_message_id}", user_id=user_id,
            account_id=account_id, vendor="sarvam", service="stt",
            operation="speech_to_text", reserved_minor=estimated_paise,
            currency="INR", cap_minor=settings.saathi_usage_account_cap_paise)
        if reservation is None:
            raise usage.UsageCapExceeded("STT account cap exceeded")
        if reservation.state != "held":
            raise usage.UsageAccountingUnavailable("STT reservation is not reusable for a new call")

    entities = await memory.surface_forms(conn, user_id)
    # Transcribe in the user's chosen language, not always Hindi. A Malayalam or
    # Gujarati speaker's voice note was previously fed to Saaras as hi-IN (LANG-2).
    lang_row = await (await conn.execute(
        "select lang_pref from users where id = %s", (user_id,))).fetchone()
    language = sarvam_lang(lang_row[0] if lang_row else None)
    transcript = await stt_mod.transcribe(wav, entities=entities, language=language)
    if reservation is not None:
        try:
            await usage.settle(conn, reservation.id, actual_minor=estimated_paise)
        except Exception:  # noqa: BLE001 -- paid call already succeeded
            log.exception("STT usage reservation settlement failed")
    # Saaras bills audio time, not bytes. The WAV supplies exact duration
    # without putting content in the ledger; failures cannot retry a success.
    try:
        await usage.record_event(
            conn, vendor="sarvam", service="stt", operation="speech_to_text",
            status="success", user_id=user_id, account_id=account_id,
            reservation_id=reservation.id if reservation else None,
            request_id=f"stt:{wa_message_id}" if wa_message_id else None,
            model=stt_mod.MODEL,
            units={"audio_seconds": seconds, "rounded_seconds": rounded_seconds},
            cost={"currency": "INR", "estimated_paise": estimated_paise},
            cost_source="catalog_estimate",
            metadata={"language": transcript.language,
                      "pricing_version": usage.SARVAM_STT_PRICE_VERSION}, latency_ms=transcript.ms)
    except Exception:  # noqa: BLE001 -- observe-only after a paid success
        log.exception("observe-only STT usage event failed")
    return transcript


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


# Backpressure for the media capability (PR-26). Two gates, because the two
# costs are different: holding a multi-MiB blob in memory is cheap and parallel,
# parsing a PDF is neither.
#
# Module-level and process-wide on purpose. The webhook detaches every message
# with `asyncio.create_task`, so "how many of these are running" is otherwise
# the sender's decision, not ours.
_MEDIA_GATE = backpressure.Gate("media", settings.saathi_media_concurrency)
_DOC_GATE = backpressure.Gate("document", settings.saathi_doc_concurrency)
# All inbound work after identity/dedupe passes this gate, including text,
# audio/STT, image/document work and the agent.  It is a process-local overload
# guard; RATE-2 below supplies the durable per-user frequency limit.
_TURN_GATE = backpressure.Gate("turn", settings.saathi_turn_concurrency)


# Refusals an elder can act on. Bilingual and specific, in the register the rest
# of the media path uses: say what happened, then say what would work. The
# person on the other end may have photographed their prescription by accident,
# and "error" is not a word they should ever see.
MEDIA_TOO_LARGE = (
    "Yeh file bahut badi hai, main ise khol nahi paungi. Jo page zaroori hai, "
    "uska photo bhej dijiye — main padh dungi. 🙏\n\n"
    "That file is too big for me to open. Send me a photo of just the page that "
    "matters and I'll read it for you."
)

MEDIA_BUSY = (
    "Main abhi ek doosri file padh rahi hoon. Ise thodi der baad dobara bhej "
    "dijiye, main zaroor padhungi. 🙏\n\n"
    "I'm reading something else just now. Please send this again in a minute and "
    "I'll read it."
)

TURN_BUSY = (
    "Main abhi bahut saare sandesh sambhaal rahi hoon. Kripya ek minute baad phir "
    "bhej dijiye. 🙏\n\n"
    "I'm handling several messages right now. Please try again in a minute."
)

TURN_RATE_LIMITED = (
    "Aapne abhi kaafi sandesh bheje hain. Kripya ek minute rukkar phir bhej dijiye. 🙏\n\n"
    "You've sent several messages just now. Please wait a minute, then send it again."
)

USAGE_CAP_LIMITED = (
    "Aaj ke liye voice-note limit poori ho gayi hai. Kripya chhota text message bhej dijiye. 🙏\n\n"
    "The voice-note limit for now is reached. Please send a short text message instead."
)

DOC_TOO_LONG = (
    "Yeh document bahut lamba hai — main itne saare page nahi padh sakti. Jis "
    "page ki baat hai, uska photo bhej dijiye.\n\n"
    "This document is very long — I can't read that many pages. Please send a "
    "photo of the page you're asking about."
)

DOC_UNREADABLE = (
    "Maaf kijiye, is file ko main padh nahi payi. Agar aap iska photo kheench "
    "kar bhej dein, to main zaroor koshish karungi. 🙏\n\n"
    "Sorry, I couldn't read that file. If you take a photo of it and send that, "
    "I'll try again."
)

MEDIA_ERROR = (
    "Maaf kijiye, yeh file main khol nahi payi. Dobara bhej sakte hain?\n\n"
    "Sorry, I couldn't open that. Could you send it again?"
)

#: Which refusal each `documents.DocumentRejected` reason earns. Unknown reasons
#: fall back to "I couldn't read it", which is true of all of them.
_DOC_REFUSALS = {"too_many_pages": DOC_TOO_LONG}


async def _handle_media(conn, transport, user_id: int, handle: str,
                        msg: dict, kind: str, wa_mid: str | None) -> dict | None:
    """Read an image or document and reply with what it says.

    Deliberately does not go through the agent loop: the vision model *is* the
    answer, and routing its output back through a text model would add latency,
    cost, and a chance of the disclaimer being paraphrased away.

    Every exit from here either sends a reading or sends a refusal. There is no
    path that drops the message silently — an elder who sent a photo and heard
    nothing back has no way to tell that from the product being broken.
    """
    node = msg.get(kind) or {}
    media_id = node.get("id")
    caption = (node.get("caption") or "").strip() or None
    mime = (node.get("mime_type") or "").lower()

    is_pdf = kind == "document" and "pdf" in mime
    # The limit is chosen from what the file *is*, not from which WhatsApp
    # bucket it arrived in — a photo sent "as a file" is still a photo, and must
    # be held to the limit the vision model will apply to it later.
    max_bytes = (settings.saathi_max_document_bytes if is_pdf
                 else settings.saathi_max_image_bytes)

    async def refuse(text: str, reason: str) -> dict:
        body = transport.format_text(text)
        await log_message(conn, user_id, "in", "image" if kind == "image" else "text",
                          wa_message_id=wa_mid, body=caption or f"[{kind}]")
        await transport.send_text(conn, user_id, handle, body)
        await log_message(conn, user_id, "out", "text", body=body)
        log.warning("media refused for user %s: %s", user_id, reason)
        return {"handled": "media_refused", "reason": reason}

    if not media_id:
        # A media message with no id is a malformed webhook, but falling through
        # is not the answer: no later capability handles a document, and the
        # agent needs text this message does not carry. She would get silence
        # for something she did send.
        log.warning("%s message %s carries no media id", kind, wa_mid)
        return await refuse(MEDIA_ERROR, "no_media_id")

    try:
        with _MEDIA_GATE.hold():
            try:
                blob = await transport.fetch_media(media_id, max_bytes)
            except MediaTooLarge:
                return await refuse(MEDIA_TOO_LARGE, "too_large")
            except Exception:  # noqa: BLE001
                log.exception("media fetch failed")
                await transport.send_text(conn, user_id, handle,
                                          transport.format_text(MEDIA_ERROR))
                return {"handled": "media_error"}

            # A transport that did not honour the limit must not be able to fail
            # open. This is the one check that measures what actually arrived.
            if len(blob) > max_bytes:
                log.error("transport %s returned %s bytes against a %s-byte limit",
                          getattr(transport, "channel", "?"), len(blob), max_bytes)
                return await refuse(MEDIA_TOO_LARGE, "too_large")

            try:
                if is_pdf:
                    # The gate covers the CPU half only — parse and rasterise.
                    # It is released before the model call, which is a network
                    # wait of 10-45s: holding a 1-of-1 slot across that would
                    # refuse every other user's document for the whole
                    # round-trip, to protect a core that is idle for it.
                    # Concurrency there is bounded by `_MEDIA_GATE` instead.
                    with _DOC_GATE.hold():
                        material = await _parse_pdf(blob)
                    reading = (None if material is None
                               else await _read_parsed(material, caption))
                elif kind == "image" or mime.startswith("image/"):
                    reading = await _look(blob, mime, caption)
                else:
                    # A .docx, a .zip, an audio file sent as a document. This
                    # used to be handed to the vision model as if it were a
                    # picture, which spent a model call to produce nothing.
                    return await refuse(DOC_UNREADABLE, "unsupported_type")
            except backpressure.Busy:
                return await refuse(MEDIA_BUSY, "busy")
            except documents.DocumentRejected as exc:
                return await refuse(_DOC_REFUSALS.get(exc.reason, DOC_UNREADABLE),
                                    exc.reason)
            except Exception:  # noqa: BLE001
                # A Bedrock throttle, a malformed response, the agent loop
                # giving up. `dispatch` would swallow this and the turn would
                # end in silence, which she cannot tell from a broken product.
                log.exception("reading media failed")
                return await refuse(MEDIA_ERROR, "read_failed")
            if reading is None:
                return await refuse(DOC_UNREADABLE, "unreadable")

            body = transport.format_text(reading.rendered())
            await log_message(conn, user_id, "in", "image" if kind == "image" else "text",
                              wa_message_id=wa_mid, body=caption or f"[{kind}]")
            await transport.send_text(conn, user_id, handle, body)
            await log_message(conn, user_id, "out", "text", body=body)
            return {"handled": "media", "kind": reading.kind,
                    "had_disclaimer": bool(reading.disclaimer)}
    except backpressure.Busy:
        # Nothing was downloaded and nothing was parsed. Say so, rather than
        # queueing a blob behind work that is already saturating the box.
        return await refuse(MEDIA_BUSY, "busy")


async def _look(blob: bytes, mime: str | None, caption: str | None) -> "vision.Reading":
    """A photograph, whichever bucket it arrived in. The caption picks the mode."""
    intent = vision.classify_intent(caption)
    if intent == "medicine":
        return await vision.describe_medicine(blob, mime)
    if intent == "document":
        return await vision.read_document(blob, mime, caption)
    return await vision.describe_image(blob, mime, caption)


async def _parse_pdf(blob: bytes) -> tuple[str, str | bytes] | None:
    """The CPU half: text layer first, rasterise page one second.

    Split from the model call so the document gate can be released between
    them. No network here — everything in this function is work the box does
    itself, which is exactly what the gate is rationing.
    """
    text = await documents.extract_text(blob)
    if documents.has_text_layer(text):
        return ("text", text)
    page = await documents.render_first_page(blob)
    return None if page is None else ("page", page)


async def _read_parsed(material: tuple[str, str | bytes],
                       caption: str | None) -> "vision.Reading":
    """The model half, run with the document gate already released."""
    how, payload = material
    if how == "text":
        return await _read_pdf_text(payload, caption)
    return await vision.read_document(payload, "image/png", caption)


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


# Command replies, per language. Onboarding stopped saying everything twice on
# 2026-07-28; these still did, so a user who chose English got a Hindi paragraph
# every time they said /stop. Same complaint, later in the journey.
CMD_COPY = {
    "hi": {
        "stopped": ("ठीक है, मैं अब संदेश नहीं भेजूँगी। "
                    "'चालू करो' कहकर वापस शुरू कर सकते हैं।"),
        "resumed": "वापस शुरू! अब मैं पहले जैसी याद दिलाऊँगी।",
        "nothing_known": "अभी मेरे पास आपके बारे में कुछ भी नहीं है।",
        "known_intro": "मेरे पास यह है:",
        "known_outro": "कुछ हटाना हो तो बताइए।",
        "cleared": ("चैट साफ़ कर दी ({n} संदेश)। आपके रिमाइंडर और "
                    "यादें वैसी ही हैं।"),
        "confirm_delete": ("क्या आप सच में सब कुछ हटाना चाहते हैं? "
                           "यह वापस नहीं आएगा।"),
        "del_yes": "हाँ, सब हटाओ", "del_no": "नहीं, रहने दो",
        "ask_lang": "आप किस भाषा में बात करना चाहेंगे?",
    },
    "hi-en": {
        "stopped": ("Theek hai, main ab message nahi bhejungi. "
                    "'chalu karo' kehkar wapas shuru kar sakte hain."),
        "resumed": "Wapas shuru! Ab main pehle jaisi yaad dilaungi.",
        "nothing_known": "Abhi mere paas aapke baare mein kuch bhi nahi hai.",
        "known_intro": "Mere paas yeh hai:",
        "known_outro": "Kuch hatana ho to bataiye.",
        "cleared": ("Chat saaf kar di ({n} message). Aapke reminders aur "
                    "yaadein waise hi hain."),
        "confirm_delete": ("Kya aap sach mein sab kuch hataana chahte hain? "
                           "Yeh wapas nahi aayega."),
        "del_yes": "Haan, sab hatao", "del_no": "Nahi, rehne do",
        "ask_lang": "Aap kis bhaasha mein baat karna chahenge?",
    },
    "en": {
        "stopped": ("Stopped — I won't send you messages. Say \"resume\" "
                    "whenever you'd like them back."),
        "resumed": "Resumed. I'll remind you as before.",
        "nothing_known": "I have nothing stored about you yet.",
        "known_intro": "Here's what I have:",
        "known_outro": "Tell me if you'd like anything removed.",
        "cleared": ("Chat cleared ({n} messages). Your reminders and memories "
                    "are untouched."),
        "confirm_delete": "Delete everything? This cannot be undone.",
        "del_yes": "Yes, delete all", "del_no": "No, keep it",
        "ask_lang": "Which language would you like to use?",
    },
    # gu/ml command copy is a first draft pending native review (LANG-2).
    "gu": {
        "stopped": ("ઠીક છે, હવે હું સંદેશા નહીં મોકલું. "
                    "'ચાલુ કરો' કહીને ફરી શરૂ કરી શકો છો."),
        "resumed": "ફરી શરૂ! હવે હું પહેલાંની જેમ યાદ કરાવીશ.",
        "nothing_known": "હમણાં મારી પાસે તમારા વિશે કંઈ નથી.",
        "known_intro": "મારી પાસે આ છે:",
        "known_outro": "કંઈ હટાવવું હોય તો કહો.",
        "cleared": ("ચેટ સાફ કરી ({n} સંદેશા). તમારા રિમાઇન્ડર અને "
                    "યાદો એવી જ છે."),
        "confirm_delete": ("શું તમે ખરેખર બધું હટાવવા માંગો છો? "
                           "આ પાછું નહીં આવે."),
        "del_yes": "હા, બધું હટાવો", "del_no": "ના, રહેવા દો",
        "ask_lang": "તમે કઈ ભાષામાં વાત કરવા માંગો છો?",
    },
    "ml": {
        "stopped": ("ശരി, ഞാൻ ഇനി സന്ദേശങ്ങൾ അയയ്ക്കില്ല. "
                    "'വീണ്ടും തുടങ്ങൂ' എന്ന് പറഞ്ഞ് തിരികെ തുടങ്ങാം."),
        "resumed": "വീണ്ടും തുടങ്ങി! ഇനി ഞാൻ പഴയതുപോലെ ഓർമ്മിപ്പിക്കാം.",
        "nothing_known": "ഇപ്പോൾ നിങ്ങളെക്കുറിച്ച് എന്റെ പക്കൽ ഒന്നുമില്ല.",
        "known_intro": "എന്റെ പക്കൽ ഇത് ഉണ്ട്:",
        "known_outro": "എന്തെങ്കിലും നീക്കം ചെയ്യണമെങ്കിൽ പറയൂ.",
        "cleared": ("ചാറ്റ് മായ്ച്ചു ({n} സന്ദേശങ്ങൾ). നിങ്ങളുടെ "
                    "ഓർമ്മപ്പെടുത്തലുകളും ഓർമ്മകളും അതേപടിയുണ്ട്."),
        "confirm_delete": ("എല്ലാം ഇല്ലാതാക്കണോ? ഇത് പിന്നെ "
                           "തിരികെ ലഭിക്കില്ല."),
        "del_yes": "അതെ, എല്ലാം ഇല്ലാതാക്കൂ", "del_no": "വേണ്ട, സൂക്ഷിക്കൂ",
        "ask_lang": "നിങ്ങൾ ഏത് ഭാഷയിൽ സംസാരിക്കാൻ ആഗ്രഹിക്കുന്നു?",
    },
}


def _c(lang: str, key: str, **fmt) -> str:
    table = CMD_COPY.get(lang) or CMD_COPY["hi"]
    out = table.get(key) or CMD_COPY["hi"][key]
    return out.format(**fmt) if fmt else out


async def _run_command(conn, transport, user_id: int, handle: str, cmd) -> dict | None:
    """Deterministic handling of unambiguous requests. No model, no cost."""
    from .agent.tools.handlers import Handlers
    from .onboarding import _lang, ASK_LANG, LANG_LIST_BUTTON, LANG_ROWS
    C = commands.Command
    lang = await _lang(conn, user_id)

    if cmd is C.LANGUAGE:
        # Re-offer the same list onboarding used. The choice was asked once and
        # could not be revisited (PR-32); the person most likely to mistap it is
        # the one this product is for.
        await transport.send_list(conn, user_id, handle, ASK_LANG,
                                  LANG_LIST_BUTTON, list(LANG_ROWS))
        return {}
    if cmd is C.HELP:
        await transport.send_text(conn, user_id, handle, HELP_TEXT)
        return {}
    if cmd is C.STOP:
        await conn.execute("update users set paused = true where id = %s", (user_id,))
        await transport.send_text(conn, user_id, handle, _c(lang, "stopped"))
        return {}
    if cmd is C.RESUME:
        await conn.execute("update users set paused = false where id = %s", (user_id,))
        await transport.send_text(conn, user_id, handle, _c(lang, "resumed"))
        return {}
    if cmd is C.WHAT_YOU_KNOW:
        known = await memory.describe(conn, user_id)
        if not known["count"]:
            body = _c(lang, "nothing_known")
        else:
            lines = [f"• {v}" for vals in known["known"].values() for v in vals]
            body = (_c(lang, "known_intro") + "\n" + "\n".join(lines) +
                    "\n\n" + _c(lang, "known_outro"))
        await transport.send_text(conn, user_id, handle, body)
        return {}
    if cmd is C.CLEAR_CHAT:
        n = await conversation.clear_conversation(conn, user_id)
        await transport.send_text(conn, user_id, handle, _c(lang, "cleared", n=n))
        return {}
    if cmd is C.DELETE_ALL:
        # Confirm once — it cannot be undone. The confirmation is a button so
        # there is no ambiguity about what "yes" meant.
        await transport.send_buttons(
            conn, user_id, handle, _c(lang, "confirm_delete"),
            [("del:yes", _c(lang, "del_yes")), ("del:no", _c(lang, "del_no"))])
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

    transport = registry.get(channel)
    handle = msg.get("from")
    wa_mid = msg.get("id")
    kind = msg.get("type", "text")

    who = await identity.resolve(conn, channel, handle, contact_name,
                                 dm_policy=settings.saathi_dm_policy)

    # Attribution capture (CAPI-1): if this message began with an ad tap, store
    # its ctwa_clid write-once. Before the admission/dedupe gates on purpose — the
    # ad click is a fact even for a handle that never gets admitted or onboards.
    # No-op unless a referral is present, so it costs a dict lookup otherwise.
    await capi.capture_referral(conn, who.user_id, msg)

    if await already_seen(conn, wa_mid):
        log.info("duplicate webhook for %s, ignoring", wa_mid)
        return {"skipped": "duplicate"}

    # A brand-new handle may present the short move code issued in a guarded
    # stale-handle chat.  Do this before admission/onboarding so the temporary
    # identity created by `resolve` never gets a second signup or an agent turn.
    text = (msg.get("text") or {}).get("body", "") if kind == "text" else ""
    move = identity.MOVE_CODE_RE.match(text)
    if move:
        moved = await identity.move_to_new_handle(conn, move.group(1), channel, handle)
        if moved:
            if transport.capabilities.has_session_window:
                await window.touch(conn, moved)
            await transport.send_text(conn, moved, handle,
                                      "Your account is now on this number. / Aapka account ab is number par hai.")
            return {"handled": "identity_move"}

    # Admission: under `pairing` an unknown handle never reaches the chain.
    if who.status == "pending" and settings.saathi_dm_policy == "pairing":
        if transport.capabilities.has_session_window:
            await window.touch(conn, who.user_id)
        if await identity.should_explain(conn, who.user_channel_id,
                                         settings.saathi_admission_max_replies):
            await transport.send_text(conn, who.user_id, handle, identity.ADMISSION_REPLY)
        log.info("unadmitted handle %s/%s — not processed", channel, handle)
        return {"skipped": "not_admitted"}

    # This gate is deliberately before window/conversation/transcription/logging
    # and the capability chain.  A recycled number must not learn stored facts,
    # cause a reminder change, or spend model/STT budget merely by sending text.
    if who.needs_reverification:
        if transport.capabilities.has_session_window:
            await window.touch(conn, who.user_id)
        button = ((msg.get("interactive") or {}).get("button_reply") or {}).get("id")
        button = button or (msg.get("button") or {}).get("payload", "")
        if button == "idv:continue":
            await identity.confirm_reverification(conn, who.user_id, who.user_channel_id)
            await transport.send_text(conn, who.user_id, handle,
                                      "Thank you. Your access is active again. / Shukriya, aapka access phir se chalu hai.")
            return {"handled": "identity_reverified"}
        if button == "idv:move":
            code = await identity.issue_link_code(conn, who.user_id, channel)
            await transport.send_text(conn, who.user_id, handle,
                                      "On your new number, send: MOVE " + code + ". This code expires in 15 minutes.")
            return {"handled": "identity_move_code"}
        await transport.send_buttons(
            conn, who.user_id, handle,
            "This number has been quiet for a while. Before I open your saved information, please confirm it is still yours. / Is number par kaafi din se baat nahi hui. Aapki saved baatein kholne se pehle, kripya confirm karein ki yeh number ab bhi aapka hai.",
            [("idv:continue", "Yes, continue"), ("idv:move", "New number")])
        return {"handled": "identity_reverification_required"}

    # This is deliberately before audio transcription and before the capability
    # chain. A rate check after either point would still spend STT/model money.
    try:
        turn_slot = _TURN_GATE.hold()
        turn_slot.__enter__()
    except backpressure.Busy:
        if transport.capabilities.has_session_window:
            await window.touch(conn, who.user_id)
        if await rate_limit.claim_notice(
                conn, who.user_id, "busy",
                cooldown_seconds=settings.saathi_limit_notice_cooldown_s):
            await transport.send_text(conn, who.user_id, handle, TURN_BUSY)
        return {"skipped": "busy"}

    try:
        allowed = await rate_limit.reserve(
            conn, who.user_id,
            limit=settings.saathi_user_turn_limit,
            window_seconds=settings.saathi_user_turn_window_s,
        )
        # A same-user request is currently making its reservation. Do not wait
        # behind it and do not contend on the notice row; quiet refusal is the
        # only response that is both bounded and free of a new queue.
        if allowed is None:
            return {"skipped": "rate_limited"}
        if not allowed:
            if transport.capabilities.has_session_window:
                await window.touch(conn, who.user_id)
            if await rate_limit.claim_notice(
                    conn, who.user_id, "rate_limit",
                    cooldown_seconds=settings.saathi_limit_notice_cooldown_s):
                await transport.send_text(conn, who.user_id, handle, TURN_RATE_LIMITED)
            return {"skipped": "rate_limited"}

        return await _handle_admitted_message(conn, transport, who, msg, kind, handle,
                                               wa_mid, channel)
    finally:
        turn_slot.__exit__(None, None, None)


async def _handle_admitted_message(conn, transport, who, msg: dict, kind: str,
                                    handle: str, wa_mid: str | None, channel: str) -> dict:
    """Run a turn that has already passed dedupe, global and user admission."""
    from .core.context import MessageContext
    from .core.handlers import dispatch

    if transport.capabilities.has_session_window:
        await window.touch(conn, who.user_id)
    convo_id = await conversation.current(conn, who.user_id, channel)

    ctx = MessageContext(
        conn=conn, transport=transport, channel=channel, handle=handle, msg=msg,
        user_id=who.user_id, display_name=who.display_name, tz=who.tz,
        voice_pref=who.voice_reply_pref,
        onboarding=await _onboarding_state(conn, who.user_id),
        lang=await onboarding._lang(conn, who.user_id),
        account_status=await accounts.status_of(conn, who.user_id),
        wa_message_id=wa_mid, kind=kind, conversation_id=convo_id,
        provenance=provenance.detect(msg, kind).value,
    )

    # Resolve text once, so every handler sees the same thing whether the user
    # typed it or spoke it.
    if kind == "audio":
        media_id = (msg.get("audio") or {}).get("id")
        try:
            ctx.transcript = await transcribe_voice(conn, who.user_id, media_id, channel,
                                                   wa_message_id=wa_mid)
        except (usage.UsageAccountingUnavailable, usage.UsageCapExceeded):
            if await rate_limit.claim_notice(
                    conn, who.user_id, "usage_cap",
                    cooldown_seconds=settings.saathi_limit_notice_cooldown_s):
                await transport.send_text(conn, who.user_id, handle, USAGE_CAP_LIMITED)
            return {"skipped": "usage_cap"}
        ctx.text = ctx.transcript.text
        if ctx.transcript.corrections:
            await _contribute_corrections(conn, who.user_id, ctx.transcript)
    elif kind in ("interactive", "button"):
        # "button" is what a template quick-reply arrives as. Treating it as
        # plain text sent the payload to the model instead of the ack handler.
        ctx.text = ctx.button_id
    else:
        ctx.text = (msg.get("text") or {}).get("body", "") or ""

    if kind not in ("interactive", "button"):
        ctx.message_id = await log_message(
            conn, who.user_id, "in", kind, wa_message_id=wa_mid, body=ctx.text,
            transcript=ctx.transcript.text if ctx.transcript else None,
            transcript_raw=ctx.transcript.raw if ctx.transcript else None,
            stt_ms=ctx.transcript.ms if ctx.transcript else None) or None
    else:
        # msg_kind has no 'button' member; both taps record as interactive.
        await log_message(conn, who.user_id, "in", "interactive",
                          wa_message_id=wa_mid, body=ctx.text)

    with observability.span("pipeline.handle_message", kind="pipeline"):
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
