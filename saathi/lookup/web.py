"""General web search, via Gemini's Google Search grounding.

AWS has no equivalent: Bedrock's Converse API accepts only tools we implement
ourselves, and Kendra indexes your own documents rather than the web. The box
has perfectly good internet — but internet access is not search. Fetching a URL
you already know is easy; *discovering which URL holds the answer* needs a
crawled index of the web, and only a handful of companies have one.

Google's is reachable through Gemini with the `google_search` tool: it returns a
grounded answer plus the sources it used, which is a better shape for us than
raw result links an elder would have to open.

**Gemini is used only as a search backend, never as the voice.** The
conversational model stays `zai.glm-5` — chosen on a measured Hinglish
entity-accuracy bakeoff and regional to ap-south-1 (decision D-D). This provider
returns retrieved text, which the agent then reports in its own words.

⚠️ **Residency:** a search query leaves India and goes to Google, unlike
everything else in this system. "Is this medicine safe with that one" is a
health-adjacent query. That is an argument for keeping look_up narrow and for
never sending the user's stored facts along with the question — this sends the
query only.
"""
from __future__ import annotations

import logging

import httpx

from .. import net_policy
from ..config import settings
from .base import Answer, register

log = logging.getLogger("saathi.lookup.web")

ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
MODEL = "gemini-2.5-flash"

# The query is sent alone. No stored facts, no name, no history — a search
# backend has no business knowing who is asking.
INSTRUCTION = (
    "Answer this question for an older adult in India, factually and briefly, "
    "in 2-3 short sentences of plain English. If the answer is uncertain or "
    "sources disagree, say so. Do not give medical, legal or financial advice.\n\n"
    "Question: "
)


class WebSearch:
    name = "web"

    def available(self) -> bool:
        return bool(settings.saathi_gemini_api_key)

    async def lookup(self, query: str, **ctx) -> Answer | None:
        q = (query or "").strip()
        if not q or not self.available():
            return None
        url = ENDPOINT.format(model=MODEL)
        net_policy.assert_safe_url(url)
        try:
            async with httpx.AsyncClient(timeout=45) as http:
                r = await http.post(
                    url, params={"key": settings.saathi_gemini_api_key},
                    json={"contents": [{"parts": [{"text": INSTRUCTION + q}]}],
                          "tools": [{"google_search": {}}]})
            if r.status_code >= 400:
                log.warning("gemini search %s: %s", r.status_code, r.text[:200])
                return None
            cand = r.json()["candidates"][0]
        except Exception:  # noqa: BLE001 - a dead provider must not kill the turn
            log.exception("gemini search failed")
            return None

        text = "".join(p.get("text", "") for p in cand.get("content", {}).get("parts", []))
        if not text.strip():
            return None
        grounding = cand.get("groundingMetadata") or {}
        sites = [(c.get("web") or {}).get("title", "")
                 for c in (grounding.get("groundingChunks") or [])]
        sites = [s for s in sites if s][:3]
        return Answer(text=text.strip()[:1200],
                      source=", ".join(sites) if sites else "Google Search",
                      extra={"grounded_sources": len(sites)})


register(WebSearch())
