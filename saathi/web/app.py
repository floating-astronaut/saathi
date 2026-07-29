"""FastAPI surface: WhatsApp webhook + health.

Only the pieces that are awkward to retrofit are real here — signature
verification, the GET verify handshake, and inbound idempotency. Message
handling itself is deliberately a stub until the channel exists.
"""
from __future__ import annotations

import hashlib
import hmac

import asyncio
import logging

from fastapi import FastAPI, Request, Response

from .. import db, net_policy, observability, pipeline
from ..config import settings

log = logging.getLogger("saathi.web")
logging.getLogger().addFilter(net_policy.RedactingFilter())

# Best-effort tracing — must never raise into a turn.
observability.init()

app = FastAPI(title="Saathi", version="0.1.0")


@app.get("/healthz")
async def healthz():
    try:
        await db.pool().open()
        return {"ok": True, "pg": await db.healthcheck(), "model": settings.saathi_model_id}
    except Exception as exc:  # noqa: BLE001
        return Response(content=f'{{"ok":false,"error":"{exc!r}"}}',
                        status_code=503, media_type="application/json")


@app.get("/webhook/whatsapp")
async def verify(request: Request):
    """Meta's subscription handshake — echo hub.challenge if the token matches."""
    q = request.query_params
    if (q.get("hub.mode") == "subscribe"
            and q.get("hub.verify_token") == settings.wa_webhook_verify_token
            and settings.wa_webhook_verify_token):
        return Response(content=q.get("hub.challenge", ""), media_type="text/plain")
    return Response(status_code=403)


def valid_signature(body: bytes, header: str | None) -> bool:
    """X-Hub-Signature-256 check. Unsigned payloads are not trusted input."""
    if not header or not settings.wa_app_secret:
        return False
    expected = "sha256=" + hmac.new(
        settings.wa_app_secret.encode(), body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, header)


def log_unhandled_fields(payload: dict) -> list[str]:
    """Name the webhook change fields we drop on the floor.

    `extract_messages` reads only `value["messages"]`, so every other field —
    `statuses`, and now that WhatsApp Pay is configured on this WABA, whatever
    Meta calls payment status — is silently discarded. Silently is the problem:
    PR-43 needs the *shape* of a real payment notification, and the honest way
    to learn it is to see one arrive rather than to guess from prose.

    Logs the field name and the value's keys. **Never the value**, which may
    carry a payer's contact details, and which we have no consent to store.
    Returns the names so a test can assert on them.
    """
    seen: list[str] = []
    for entry in payload.get("entry", []) or []:
        for change in entry.get("changes", []) or []:
            field = change.get("field")
            value = change.get("value") or {}
            if "messages" in value:
                continue
            seen.append(field or "?")
            log.info("unhandled webhook field %r with keys %s",
                     field, sorted(value.keys()))
    return seen


async def _process(payload: dict) -> None:
    """Do the work off the request path. Meta times webhooks out quickly and
    retries on non-2xx, so a slow STT or model call must never delay the ack."""
    log_unhandled_fields(payload)
    await db.pool().open()
    for msg, name in pipeline.extract_messages(payload):
        try:
            async with db.pool().connection() as conn:
                result = await pipeline.handle_message(conn, msg, name)
                log.info("handled %s -> %s", msg.get("id"), result)
        except Exception:  # noqa: BLE001 - one bad message must not stop the rest
            log.exception("failed handling %s", msg.get("id"))


@app.post("/webhook/whatsapp")
async def receive(request: Request):
    body = await request.body()
    if not valid_signature(body, request.headers.get("X-Hub-Signature-256")):
        return Response(status_code=403)
    payload = await request.json()
    # Ack immediately; idempotency is enforced by messages.wa_message_id.
    asyncio.create_task(_process(payload))
    return {"ok": True}
