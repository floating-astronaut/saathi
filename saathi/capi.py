"""Click-to-WhatsApp (CTWA) conversion attribution — Conversions API, Model B.

Two halves, both content-free:

  * `capture_referral` reads the `ctwa_clid` Meta puts on the first message of a
    conversation that began with an ad tap, and stores it write-once against the
    user. It runs for every inbound message but does nothing unless a referral is
    present, so it costs a dict lookup on the common path.
  * `report_lead`, on onboarding completion, sends one `LeadSubmitted` to the
    dataset so Meta can attribute the signup to the ad that drove it.

What leaves the box is the click id Meta minted, an event name and a timestamp —
never message content, never elder PII. With CTWA the `ctwa_clid` is the match
key, so the event carries nothing about the person. This is deliberately *not*
the Automatic Events API, which would have Meta run NLP over elders' threads; we
send our own signal instead. See docs/CAPI_GATEWAY.md and docs/DECISIONS.md.

Same discipline as metrics.py: **this must never raise into a user turn.** A
signup that succeeded must not be undone because an attribution ping failed.
"""
from __future__ import annotations

import logging
import time

import httpx

from .config import settings

log = logging.getLogger("saathi.capi")

GRAPH = "https://graph.facebook.com/v21.0"


def _clid_from(msg: dict) -> str | None:
    """The ctwa_clid on this message, or None. Defensive against odd shapes."""
    ref = msg.get("referral")
    if isinstance(ref, dict):
        clid = ref.get("ctwa_clid")
        if isinstance(clid, str) and clid:
            return clid
    return None


async def capture_referral(conn, user_id: int, msg: dict) -> None:
    """Store the ad click id write-once. No-op unless the message carries one.

    Set only while `ctwa_clid` is null so the *first* ad click — the one that
    started the relationship — wins over any later one, and so a re-delivered
    webhook is idempotent.
    """
    clid = _clid_from(msg)
    if not clid:
        return
    try:
        await conn.execute(
            "update users set ctwa_clid = %s, ctwa_captured_at = now() "
            "where id = %s and ctwa_clid is null",
            (clid, user_id))
    except Exception:  # noqa: BLE001 — attribution must never break a turn
        log.exception("ctwa capture failed for user %s (non-fatal)", user_id)


def _build_event(clid: str) -> dict:
    """The CAPI event body. Has room only for the click id, name and time —
    there is nowhere here to put message content, which is the point."""
    return {
        "event_name": "LeadSubmitted",
        "event_time": int(time.time()),
        "action_source": "business_messaging",
        "messaging_channel": "whatsapp",
        "user_data": {
            "whatsapp_business_account_id": settings.wa_business_account_id,
            "ctwa_clid": clid,
        },
    }


async def report_lead(conn, user_id: int) -> bool:
    """On onboarding completion, report a LeadSubmitted if this user came from an
    ad. Returns whether an event was sent. Never raises.

    Skips cleanly when: no dataset is configured (feature off), the user has no
    captured click id (organic signup), or Meta is unreachable.
    """
    if not settings.saathi_capi_dataset_id:
        return False
    try:
        row = await (await conn.execute(
            "select ctwa_clid from users where id = %s", (user_id,))).fetchone()
    except Exception:  # noqa: BLE001
        log.exception("ctwa lookup failed for user %s (non-fatal)", user_id)
        return False
    clid = row[0] if row else None
    if not clid:
        return False  # organic signup — nothing to attribute

    payload: dict = {"data": [_build_event(clid)]}
    # When set, the event shows only in Events Manager's Test Events tab and does
    # not touch production attribution — the safe way to verify end to end.
    if settings.saathi_capi_test_event_code:
        payload["test_event_code"] = settings.saathi_capi_test_event_code

    try:
        async with httpx.AsyncClient(timeout=8.0) as http:
            r = await http.post(
                f"{GRAPH}/{settings.saathi_capi_dataset_id}/events",
                params={"access_token": settings.wa_access_token},
                json=payload)
        if r.status_code == 200 and r.json().get("events_received", 0) >= 1:
            log.info("ctwa LeadSubmitted reported for user %s", user_id)
            return True
        log.warning("ctwa report for user %s not accepted: HTTP %s %s",
                    user_id, r.status_code, r.text[:200])
    except Exception:  # noqa: BLE001 — a failed ping must not undo a signup
        log.exception("ctwa report failed for user %s (non-fatal)", user_id)
    return False
