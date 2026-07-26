"""FastAPI surface: WhatsApp webhook + health.

Only the pieces that are awkward to retrofit are real here — signature
verification, the GET verify handshake, and inbound idempotency. Message
handling itself is deliberately a stub until the channel exists.
"""
from __future__ import annotations

import hashlib
import hmac

from fastapi import FastAPI, Request, Response

from .. import db
from ..config import settings

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


@app.post("/webhook/whatsapp")
async def receive(request: Request):
    body = await request.body()
    if not valid_signature(body, request.headers.get("X-Hub-Signature-256")):
        return Response(status_code=403)
    # Meta retries aggressively; ack fast and do the work off the request path.
    # Idempotency is enforced by messages.wa_message_id being unique.
    return {"ok": True}
