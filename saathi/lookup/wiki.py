"""Encyclopaedic lookup — "who was X", "what is Y".

Wikipedia's REST summary endpoint is keyless, fast, and returns a short lead
paragraph, which is the right shape for a WhatsApp reply. It is deliberately
*not* a general web search: it answers settled questions well and current
events badly, and pretending otherwise would be worse than declining.
"""
from __future__ import annotations

import logging
import urllib.parse

import httpx

from .. import net_policy
from .base import Answer, register

log = logging.getLogger("saathi.lookup.wiki")

SEARCH = "https://en.wikipedia.org/w/rest.php/v1/search/page"
SUMMARY = "https://en.wikipedia.org/api/rest_v1/page/summary/"

# Wikipedia rejects or throttles unidentified clients, and returns HTML rather
# than JSON when it does — which is why this failed silently at first.
HEADERS = {"User-Agent": "Saathi/0.1 (eldercare assistant; help.nuraveda@gmail.com)",
           "Accept": "application/json"}


class Wikipedia:
    name = "wikipedia"

    def available(self) -> bool:
        return True

    async def lookup(self, query: str, **ctx) -> Answer | None:
        q = (query or "").strip()
        if not q:
            return None
        async with httpx.AsyncClient(timeout=15, follow_redirects=True,
                                     headers=HEADERS) as http:
            s_url = f"{SEARCH}?q={urllib.parse.quote(q)}&limit=1"
            net_policy.assert_safe_url(s_url)
            r = await http.get(s_url)
            if r.status_code >= 400 or "json" not in r.headers.get("content-type", ""):
                log.warning("wikipedia search %s: %s", r.status_code,
                            r.headers.get("content-type"))
                return None
            pages = r.json().get("pages") or []
            if not pages:
                return None
            key = pages[0].get("key")
            sum_url = SUMMARY + urllib.parse.quote(key, safe="")
            net_policy.assert_safe_url(sum_url)
            r = await http.get(sum_url)
            if r.status_code >= 400:
                return None
            d = r.json()
        extract = (d.get("extract") or "").strip()
        if not extract:
            return None
        return Answer(text=extract[:900],
                      source="Wikipedia",
                      url=(d.get("content_urls", {}).get("desktop", {}) or {}).get("page"))


register(Wikipedia())
