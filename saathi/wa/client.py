"""WhatsApp Cloud API client — Meta direct (decision D-A).

Every outbound path funnels through `_send`, which calls the window guard
first. That is the point: it should be impossible to send free-form outside
the 24-hour window by forgetting to check, because you cannot reach the wire
without passing the check.

Media note (PRD §9): inbound voice notes are OGG/Opus and their media URLs
expire in minutes — fetch immediately. Outbound audio must also be OGG/Opus or
WhatsApp renders a file attachment instead of a voice-note bubble, which for an
elder is the difference between "I understand this" and "what is this".
"""
from __future__ import annotations

import logging

import httpx

from ..channels.base import MediaTooLarge
from ..config import settings
from .window import Channel, assert_can_send

log = logging.getLogger("saathi.wa")

GRAPH = "https://graph.facebook.com/v21.0"


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {settings.wa_access_token}",
            "Content-Type": "application/json"}


def _describe(payload: dict) -> tuple[str, str | None, str | None]:
    """(kind, body_text, template_name) for the `messages` row.

    Derived from the wire payload rather than passed in by the caller, so a new
    send helper cannot quietly skip being recorded.
    """
    t = payload.get("type")
    if t == "text":
        return "text", (payload.get("text") or {}).get("body"), None
    if t == "interactive":
        inter = payload.get("interactive") or {}
        return "interactive", (inter.get("body") or {}).get("text"), None
    if t == "template":
        tpl = payload.get("template") or {}
        params: list[str] = []
        for c in tpl.get("components", []):
            if c.get("type") == "body":
                params = [p.get("text") for p in c.get("parameters", []) if p.get("text")]
        # The variables are what the user actually read; the fixed body lives in
        # the approved template and is recoverable from its name.
        return "template", (" · ".join(params) or None), tpl.get("name")
    if t in ("audio", "image"):
        return t, None, None
    return "text", None, None


async def _record_outbound(conn, user_id: int, wa_message_id: str, payload: dict) -> None:
    """Record every outbound message. Here, not in the callers.

    Onboarding sent five messages to the first real user and recorded none of
    them: it calls the transport directly, and only `pipeline` and the reminder
    worker remembered to insert afterwards. So the consent text a user was shown
    was absent from `messages` — the table the 6-hourly backup actually protects
    — while `consent_at` claimed they had agreed to it.

    A record that depends on every caller remembering is a record with holes in
    it. This is the single wire path; recording here cannot be forgotten.

    Never raises: the message has already gone out. Failing the caller here would
    invite a resend of something the user has read.
    """
    kind, body, template = _describe(payload)
    try:
        await conn.execute(
            """insert into messages (user_id, direction, kind, wa_message_id,
                                     body_text, template_name)
               values (%s,'out',%s,%s,%s,%s)
               on conflict (wa_message_id) do nothing""",
            (user_id, kind, wa_message_id, body, template))
    except Exception:
        log.exception("outbound %s was sent but not recorded", wa_message_id)


async def _send(conn, user_id: int, wa_id: str, payload: dict, channel: Channel) -> str:
    """The single wire path. Returns the WhatsApp message id."""
    await assert_can_send(conn, user_id, channel)
    body = {"messaging_product": "whatsapp", "recipient_type": "individual",
            "to": wa_id, **payload}
    url = f"{GRAPH}/{settings.wa_phone_number_id}/messages"
    async with httpx.AsyncClient(timeout=20) as http:
        r = await http.post(url, headers=_headers(), json=body)
        if r.status_code >= 400:
            log.error("cloud api %s: %s", r.status_code, r.text[:400])
        r.raise_for_status()
        mid = r.json()["messages"][0]["id"]
    await _record_outbound(conn, user_id, mid, payload)
    return mid


async def send_text(conn, user_id: int, wa_id: str, text: str) -> str:
    """Free-form text. Only valid inside the window."""
    return await _send(conn, user_id, wa_id,
                       {"type": "text", "text": {"preview_url": False, "body": text}},
                       Channel.FREEFORM)


async def send_order_details(conn, user_id: int, wa_id: str, payload: dict) -> str:
    """Send a pre-built `order_details` invoice.

    Takes the payload rather than building it: the amount and reference are
    decided in `saathi.payments`, which is the single place allowed to say what
    someone owes. This function only puts it on the wire.

    `Channel.FREEFORM` because an invoice is a normal in-window message. That is
    fine for the paywall, which only ever fires in reply to something the user
    just sent — so the 24-hour window is open by construction. An invoice sent
    from the worker, unprompted, would need a template and does not exist.
    """
    return await _send(conn, user_id, wa_id, payload, Channel.FREEFORM)


async def send_buttons(conn, user_id: int, wa_id: str, body: str,
                       buttons: list[tuple[str, str]]) -> str:
    """Up to 3 quick-reply buttons, 20 chars each (§11).

    Buttons beat free text wherever the choice is bounded — errorless-by-default
    (§6.6). We truncate rather than let Meta reject the whole message.
    """
    if len(buttons) > 3:
        raise ValueError("WhatsApp allows at most 3 quick-reply buttons")
    return await _send(conn, user_id, wa_id, {
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": body},
            "action": {"buttons": [
                {"type": "reply", "reply": {"id": bid, "title": title[:20]}}
                for bid, title in buttons]},
        },
    }, Channel.FREEFORM)


async def send_list(conn, user_id: int, wa_id: str, body: str,
                    button: str, rows: list[tuple[str, str]]) -> str:
    """An interactive **list** message — up to 10 tappable rows (§11).

    Used where the choice has more options than the three quick-reply buttons
    allow — the language picker outgrew buttons when Gujarati and Malayalam were
    added (LANG-2). `button` is the label that opens the list (≤20 chars); each
    row is (id, title), title ≤24 chars. Truncated rather than letting Meta
    reject the whole message.
    """
    if not rows:
        raise ValueError("a list message needs at least one row")
    if len(rows) > 10:
        raise ValueError("WhatsApp allows at most 10 list rows")
    return await _send(conn, user_id, wa_id, {
        "type": "interactive",
        "interactive": {
            "type": "list",
            "body": {"text": body},
            "action": {
                "button": button[:20],
                "sections": [{"rows": [
                    {"id": rid, "title": title[:24]} for rid, title in rows]}],
            },
        },
    }, Channel.FREEFORM)


async def send_cta_url(conn, user_id: int, wa_id: str, body: str,
                       label: str, url: str) -> str:
    """CTA URL button, so the raw link never appears in the message body (§11)."""
    return await _send(conn, user_id, wa_id, {
        "type": "interactive",
        "interactive": {
            "type": "cta_url",
            "body": {"text": body},
            "action": {"name": "cta_url",
                       "parameters": {"display_text": label[:20], "url": url}},
        },
    }, Channel.FREEFORM)


async def send_template(conn, user_id: int, wa_id: str, name: str,
                        lang: str = "en", variables: list[str] | None = None,
                        payloads: list[str] | None = None) -> str:
    """Pre-approved template. The only thing deliverable outside the window.

    A template's job is not to say everything — it is to *get a reply*, which
    reopens the free window (§11).

    `payloads` sets the quick-reply payload per button, in template order. The
    approved templates already carry the buttons ("Ho gaya", "15 min baad"); a
    template quick-reply returns only its *label* unless a `button` component
    supplies a payload per message. Without one there is nothing to tie a tap to
    the turn that produced it, which is why acknowledgements never worked
    (PR-4b).
    """
    components = []
    if variables:
        components.append({"type": "body",
                           "parameters": [{"type": "text", "text": v} for v in variables]})
    for i, payload in enumerate(payloads or []):
        components.append({"type": "button", "sub_type": "quick_reply",
                           "index": str(i),
                           "parameters": [{"type": "payload", "payload": payload}]})
    mid = await _send(conn, user_id, wa_id, {
        "type": "template",
        "template": {"name": name, "language": {"code": lang}, "components": components},
    }, Channel.TEMPLATE)
    # The Meta id exists only after the send succeeds. Observe-only accounting
    # must never turn that already-delivered message into a caller retry.
    try:
        from .. import usage
        row = await (await conn.execute("select account_id from users where id = %s", (user_id,))).fetchone()
        await usage.record_event(conn, vendor="whatsapp", service="template",
                                 operation="send_template", status="success", user_id=user_id,
                                 account_id=row[0] if row else None, request_id=mid, model=name,
                                 units={"template_messages": 1},
                                 metadata={"language": lang})
    except Exception:
        log.exception("observe-only template usage event failed after %s", mid)
    return mid


async def send_audio(conn, user_id: int, wa_id: str, media_id: str) -> str:
    """Send a previously-uploaded OGG/Opus voice note."""
    return await _send(conn, user_id, wa_id,
                       {"type": "audio", "audio": {"id": media_id}}, Channel.FREEFORM)


async def send_voice_note(conn, user_id: int, wa_id: str, text: str, lang: str,
                          *, wa_message_id: str | None = None) -> str | None:
    """Speak `text` as a voice note (PR-8, D-AE). Best-effort: any failure logs
    and returns None, because the text reply has already been sent and a broken
    voice note must not surface as a broken turn.

    Metered through the usage ledger exactly like STT — a content-free
    `sarvam/tts` event per real synthesis, and a pre-call cap when the global
    enforcement flag is on. A cache hit spends nothing and records nothing.
    """
    from .. import usage
    from ..speech import tts

    row = await (await conn.execute(
        "select account_id from users where id = %s", (user_id,))).fetchone()
    account_id = row[0] if row else None

    reservation = None
    est_paise = usage.sarvam_tts_cost_paise(
        len(text or ""), paise_per_1k=settings.saathi_sarvam_tts_paise_per_1k_chars)
    if usage.enforcement_enabled(
            enabled=settings.saathi_usage_enforcement_enabled,
            mode=settings.saathi_usage_ledger_mode,
            account_cap_paise=settings.saathi_usage_account_cap_paise):
        if account_id is None or not wa_message_id:
            log.warning("tts skipped: enforcement on but no account/idempotency key")
            return None
        reservation = await usage.reserve(
            conn, idempotency_key=f"tts:{wa_message_id}", user_id=user_id,
            account_id=account_id, vendor="sarvam", service="tts",
            operation="text_to_speech", reserved_minor=est_paise,
            currency="INR", cap_minor=settings.saathi_usage_account_cap_paise)
        if reservation is None or reservation.state != "held":
            # Cap exceeded or a stale reservation — skip voice, keep the text reply.
            log.info("tts skipped: usage cap for user %s", user_id)
            return None

    try:
        speech = await tts.synthesize_ogg(text, lang)
        media_id = await upload_media(speech.ogg, "audio/ogg")
        mid = await send_audio(conn, user_id, wa_id, media_id)
    except Exception:
        log.exception("tts voice note failed for user %s", user_id)
        if reservation is not None:
            await usage.release(conn, reservation.id)
        return None

    actual_paise = 0 if speech.cached else usage.sarvam_tts_cost_paise(
        speech.chars, paise_per_1k=settings.saathi_sarvam_tts_paise_per_1k_chars)
    if reservation is not None:
        try:
            await usage.settle(conn, reservation.id, actual_minor=actual_paise)
        except Exception:
            log.exception("tts usage settlement failed")
    if not speech.cached:
        # No vendor call on a cache hit -> nothing to bill or record.
        try:
            await usage.record_event(
                conn, vendor="sarvam", service="tts", operation="text_to_speech",
                status="ok", user_id=user_id, account_id=account_id,
                reservation_id=reservation.id if reservation else None,
                model=settings.saathi_tts_model, request_id=speech.request_id,
                units={"characters": speech.chars},
                cost={"minor": actual_paise, "currency": "INR"},
                cost_source="catalog_estimate", latency_ms=speech.ms)
        except Exception:
            log.exception("tts usage event failed")
    return mid


def _as_int(value) -> int | None:
    """An advertised size, or None if we could not establish one."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


async def fetch_media(media_id: str, max_bytes: int) -> bytes:
    """Resolve a media id and download it. Do this immediately — URLs expire.

    `max_bytes` has no default on purpose. WhatsApp accepts documents up to
    100 MB and this box has 8 GiB shared with everything else, so a call site
    that forgot to say what it could afford would be the whole of PR-26 back
    again. The size is checked three times, cheapest first:

    1. **Meta's own `file_size`**, from the metadata call — this costs no
       bandwidth at all, so a 90 MB PDF is refused before a byte moves.
    2. **`Content-Length`** on the download response.
    3. **The bytes as they arrive.** Both of the above are supplied by someone
       else. This one is not, and it is the one that actually holds: the
       response is streamed and abandoned the moment it exceeds the limit,
       rather than buffered in full and measured afterwards.

    A size we could not determine is *not* treated as small — 1 and 2 are
    advisory and only 3 decides.
    """
    if not isinstance(max_bytes, int) or max_bytes < 1:
        raise ValueError(f"fetch_media needs a positive byte limit, got {max_bytes!r}")

    async with httpx.AsyncClient(timeout=30) as http:
        meta = await http.get(f"{GRAPH}/{media_id}", headers=_headers())
        meta.raise_for_status()
        info = meta.json()
        url = info["url"]

        declared = _as_int(info.get("file_size"))
        if declared is None:
            log.warning("media %s advertised no usable file_size; streaming under cap",
                        media_id)
        elif declared > max_bytes:
            raise MediaTooLarge(media_id, declared, max_bytes)

        # The CDN URL still needs the bearer token.
        headers = {"Authorization": f"Bearer {settings.wa_access_token}"}
        buf = bytearray()
        async with http.stream("GET", url, headers=headers) as resp:
            resp.raise_for_status()
            length = _as_int(resp.headers.get("content-length"))
            if length is not None and length > max_bytes:
                raise MediaTooLarge(media_id, length, max_bytes)
            async for chunk in resp.aiter_bytes():
                buf += chunk
                if len(buf) > max_bytes:
                    # Leaving the block closes the connection; the rest of the
                    # file is never transferred.
                    raise MediaTooLarge(media_id, None, max_bytes)
        return bytes(buf)


async def upload_media(data: bytes, mime: str = "audio/ogg") -> str:
    """Upload outbound audio, returning a media id usable with send_audio."""
    url = f"{GRAPH}/{settings.wa_phone_number_id}/media"
    async with httpx.AsyncClient(timeout=60) as http:
        r = await http.post(
            url,
            headers={"Authorization": f"Bearer {settings.wa_access_token}"},
            data={"messaging_product": "whatsapp", "type": mime},
            files={"file": ("voice.ogg", data, mime)},
        )
        r.raise_for_status()
        return r.json()["id"]
