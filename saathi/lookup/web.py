"""General web search, via Gemini's Google Search grounding.

AWS has no equivalent: Bedrock's Converse API accepts only tools we implement
ourselves, and Kendra indexes your own documents rather than the web. The box
has perfectly good internet — but internet access is not search. Fetching a URL
you already know is easy; *discovering which URL holds the answer* needs a
crawled index, and only a handful of companies have one.

Two routes to the same model, preferred in order:

1. **Vertex AI in `asia-south1` (Mumbai)** with Saathi's own service account.
   The request is served from India, which matters because search is otherwise
   the only part of this system that leaves the country. Needs billing enabled
   on the Saathi GCP project.
2. **AI Studio** with an API key. Works without billing, but the endpoint is
   global.

Google Search itself is global either way; what the region changes is where the
request is served and where the model runs.

**Gemini is used only as a search backend, never as the voice.** The
conversational model stays `zai.glm-5` — chosen on a measured Hinglish
entity-accuracy bakeoff and regional to ap-south-1 (decision D-D). This provider
returns retrieved text, which the agent then reports in its own words.
"""
from __future__ import annotations

import json
import logging

import httpx

from .. import net_policy
from ..config import settings
from .base import Answer, register

log = logging.getLogger("saathi.lookup.web")

MODEL = "gemini-2.5-flash"
VERTEX_LOCATION = "asia-south1"
VERTEX = ("https://{loc}-aiplatform.googleapis.com/v1/projects/{project}"
          "/locations/{loc}/publishers/google/models/{model}:generateContent")
AI_STUDIO = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

# The question is sent alone. No stored facts, no name, no history — a search
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
        return bool(settings.saathi_gcp_sa_file or settings.saathi_gemini_api_key)

    # --- credentials ---------------------------------------------------------

    def _vertex(self) -> tuple[str, str] | None:
        """(bearer token, project id), or None if the service account is unusable."""
        if not settings.saathi_gcp_sa_file:
            return None
        try:
            import google.auth.transport.requests as gr
            from google.oauth2 import service_account
            creds = service_account.Credentials.from_service_account_file(
                settings.saathi_gcp_sa_file,
                scopes=["https://www.googleapis.com/auth/cloud-platform"])
            creds.refresh(gr.Request())
            with open(settings.saathi_gcp_sa_file) as fh:
                project = json.load(fh).get("project_id", settings.saathi_gcp_project)
            return creds.token, project
        except Exception:  # noqa: BLE001 - fall back to the key rather than fail
            log.exception("vertex credentials unusable; will try AI Studio")
            return None

    def _routes(self, q: str) -> list[tuple[str, dict, dict | None, dict]]:
        """Ordered (url, headers, params, body) attempts."""
        out: list[tuple[str, dict, dict | None, dict]] = []
        tok = self._vertex()
        if tok:
            bearer, project = tok
            out.append((
                VERTEX.format(loc=VERTEX_LOCATION, project=project, model=MODEL),
                {"Authorization": f"Bearer {bearer}", "Content-Type": "application/json"},
                None,
                {"contents": [{"role": "user", "parts": [{"text": INSTRUCTION + q}]}],
                 "tools": [{"googleSearch": {}}]},
            ))
        if settings.saathi_gemini_api_key:
            out.append((
                AI_STUDIO.format(model=MODEL),
                {"Content-Type": "application/json"},
                {"key": settings.saathi_gemini_api_key},
                {"contents": [{"parts": [{"text": INSTRUCTION + q}]}],
                 "tools": [{"google_search": {}}]},
            ))
        return out

    # --- lookup --------------------------------------------------------------

    async def lookup(self, query: str, **ctx) -> Answer | None:
        q = (query or "").strip()
        if not q or not self.available():
            return None

        candidate = None
        for url, headers, params, body in self._routes(q):
            net_policy.assert_safe_url(url)
            try:
                async with httpx.AsyncClient(timeout=45) as http:
                    r = await http.post(url, headers=headers, params=params, json=body)
            except Exception:  # noqa: BLE001 - try the next route
                log.exception("search request failed via %s", url.split("/")[2])
                continue
            if r.status_code >= 400:
                # 403 on Vertex is usually "billing not enabled" — fall through
                # to the next route rather than failing the user's question.
                log.warning("search %s via %s: %s", r.status_code,
                            url.split("/")[2], r.text[:160])
                continue
            try:
                candidate = r.json()["candidates"][0]
                break
            except Exception:  # noqa: BLE001
                log.exception("unexpected search response shape")
                continue

        if candidate is None:
            return None

        text = "".join(p.get("text", "")
                       for p in candidate.get("content", {}).get("parts", []))
        if not text.strip():
            return None
        grounding = candidate.get("groundingMetadata") or {}
        sites = [(c.get("web") or {}).get("title", "")
                 for c in (grounding.get("groundingChunks") or [])]
        sites = [s for s in sites if s][:3]
        return Answer(text=text.strip()[:1200],
                      source=", ".join(sites) if sites else "Google Search",
                      extra={"grounded_sources": len(sites)})


register(WebSearch())
