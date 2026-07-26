"""General web search — the slot a paid provider fills.

No key is configured today (`SERPAPI_API_KEY` exists but is empty), so this
reports itself unavailable and the agent simply does not offer it. That is the
honest behaviour: a provider that silently returns nothing looks like a bug,
while one that declares itself unavailable is a configuration fact.

Serper is the assumed shape because it is cheap and returns clean JSON. Swapping
to Brave or SerpAPI is this file only.
"""
from __future__ import annotations

import logging

import httpx

from .. import net_policy
from ..config import settings
from .base import Answer, register

log = logging.getLogger("saathi.lookup.web")

ENDPOINT = "https://google.serper.dev/search"


class WebSearch:
    name = "web"

    def available(self) -> bool:
        return bool(settings.saathi_search_api_key)

    async def lookup(self, query: str, **ctx) -> Answer | None:
        if not self.available():
            return None
        net_policy.assert_safe_url(ENDPOINT)
        async with httpx.AsyncClient(timeout=20) as http:
            r = await http.post(
                ENDPOINT,
                headers={"X-API-KEY": settings.saathi_search_api_key,
                         "Content-Type": "application/json"},
                json={"q": query, "gl": "in", "hl": "en", "num": 4})
            if r.status_code >= 400:
                log.warning("search %s: %s", r.status_code, r.text[:200])
                return None
            d = r.json()

        # Prefer the answer box; fall back to the top organic results.
        if d.get("answerBox", {}).get("answer"):
            return Answer(text=d["answerBox"]["answer"], source="web search")
        lines, first_url = [], None
        for hit in (d.get("organic") or [])[:3]:
            snippet = (hit.get("snippet") or "").strip()
            if snippet:
                lines.append(f"- {snippet}")
                first_url = first_url or hit.get("link")
        if not lines:
            return None
        return Answer(text="\n".join(lines), source="web search", url=first_url)


register(WebSearch())
