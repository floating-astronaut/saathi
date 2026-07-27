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
    except Exception:  # noqa: BLE001 - the send succeeded; only the record failed
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
    return await _send(conn, user_id, wa_id, {
        "type": "template",
        "template": {"name": name, "language": {"code": lang}, "components": components},
    }, Channel.TEMPLATE)


async def send_audio(conn, user_id: int, wa_id: str, media_id: str) -> str:
    """Send a previously-uploaded OGG/Opus voice note."""
    return await _send(conn, user_id, wa_id,
                       {"type": "audio", "audio": {"id": media_id}}, Channel.FREEFORM)


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
