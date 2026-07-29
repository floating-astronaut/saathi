"""Fail-loud check that Meta has not taken over Saathi's WhatsApp responder."""
from __future__ import annotations

import asyncio
import logging

import httpx

from .config import settings

log = logging.getLogger("saathi.meta_guard")


async def check(http: httpx.AsyncClient) -> None:
    if not (settings.wa_app_id and settings.wa_app_secret and settings.wa_phone_number_id):
        raise RuntimeError("Meta guard is unconfigured")
    app_token = f"{settings.wa_app_id}|{settings.wa_app_secret}"
    r = await http.get(
        f"https://graph.facebook.com/v21.0/{settings.wa_app_id}/subscriptions?fields=object,fields",
        headers={"Authorization": f"Bearer {app_token}"},
    )
    r.raise_for_status()
    rows = r.json().get("data")
    if not isinstance(rows, list) or not any(
        x.get("object") == "whatsapp_business_account"
        and any(f.get("name") == "messages" for f in x.get("fields", []))
        for x in rows if isinstance(x, dict)
    ):
        raise RuntimeError("Saathi app is not subscribed to WhatsApp messages")

    r = await http.get(
        f"https://api.facebook.com/{settings.wa_phone_number_id}/agent_config/settings",
        headers={"Authorization": f"Bearer {settings.wa_access_token}"},
    )
    r.raise_for_status()
    agent = r.json()
    if agent not in ([], None):
        raise RuntimeError("Meta Business Agent settings are present; refusing silent takeover")


async def main() -> None:
    async with httpx.AsyncClient(timeout=15) as http:
        await check(http)
    log.info("Meta responder guard passed")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
