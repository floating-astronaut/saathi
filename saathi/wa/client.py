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

from ..config import settings
from .window import Channel, assert_can_send

log = logging.getLogger("saathi.wa")

GRAPH = "https://graph.facebook.com/v21.0"


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {settings.wa_access_token}",
            "Content-Type": "application/json"}


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
        return r.json()["messages"][0]["id"]


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
                        lang: str = "en", variables: list[str] | None = None) -> str:
    """Pre-approved template. The only thing deliverable outside the window.

    A template's job is not to say everything — it is to *get a reply*, which
    reopens the free window (§11).
    """
    components = []
    if variables:
        components.append({"type": "body",
                           "parameters": [{"type": "text", "text": v} for v in variables]})
    return await _send(conn, user_id, wa_id, {
        "type": "template",
        "template": {"name": name, "language": {"code": lang}, "components": components},
    }, Channel.TEMPLATE)


async def send_audio(conn, user_id: int, wa_id: str, media_id: str) -> str:
    """Send a previously-uploaded OGG/Opus voice note."""
    return await _send(conn, user_id, wa_id,
                       {"type": "audio", "audio": {"id": media_id}}, Channel.FREEFORM)


async def fetch_media(media_id: str) -> bytes:
    """Resolve a media id and download it. Do this immediately — URLs expire."""
    async with httpx.AsyncClient(timeout=30) as http:
        meta = await http.get(f"{GRAPH}/{media_id}", headers=_headers())
        meta.raise_for_status()
        url = meta.json()["url"]
        # The CDN URL still needs the bearer token.
        blob = await http.get(url, headers={"Authorization": f"Bearer {settings.wa_access_token}"})
        blob.raise_for_status()
        return blob.content


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
