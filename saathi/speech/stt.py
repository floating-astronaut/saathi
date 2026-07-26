"""Sarvam Saaras speech-to-text.

PRD §9: STT is the product, TTS is a commodity. Inbound speech is an open set —
disfluent, code-mixed, noisy, full of proper nouns no general model has seen.
`codemix` is the right default for Hinglish.

The pipeline this sits in (§10):
    OGG/Opus -> ffmpeg -> WAV16k -> Saaras -> entity correction -> intent

Entity biasing: the PRD flags "check whether Saaras v3 supports keyword
boosting" as the single biggest available accuracy win. We send the vocabulary
when the API accepts it and fall back to the local correction pass either way,
so the caller's behaviour does not change with the answer.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

import httpx

from ..config import settings
from .correct import Corrected, correct

log = logging.getLogger("saathi.stt")

ENDPOINT = "https://api.sarvam.ai/speech-to-text"
MODEL = "saaras:v3"
# Voice notes are almost always <30s, which is the REST path's limit (§9).
MAX_SECONDS = 30


@dataclass
class Transcript:
    raw: str                       # straight from the model, kept for eval scoring
    text: str                      # after entity correction — what the agent sees
    language: str | None = None
    ms: int = 0
    corrections: list = field(default_factory=list)

    @property
    def repaired(self) -> bool:
        return bool(self.corrections)


class STTError(RuntimeError):
    pass


async def transcribe(wav: bytes, entities: list[str] | None = None,
                     language: str = "hi-IN", mode: str = "codemix") -> Transcript:
    """Transcribe a 16 kHz mono WAV, then repair it against known entities.

    `entities` are the user's medicine/person/place names from memory. They are
    offered to the API as a bias vocabulary and always used locally afterwards.
    """
    if not settings.sarvam_api_key:
        raise STTError("SARVAM_API_KEY not set")

    started = time.monotonic()
    data = {"model": MODEL, "language_code": language, "mode": mode}
    if entities:
        # Best-effort: ignored by the API if unsupported, which is why the
        # local correction pass is the contract rather than the fallback.
        data["prompt"] = ", ".join(entities[:50])

    async with httpx.AsyncClient(timeout=45) as http:
        r = await http.post(
            ENDPOINT,
            headers={"api-subscription-key": settings.sarvam_api_key},
            data=data,
            files={"file": ("audio.wav", wav, "audio/wav")},
        )
        if r.status_code >= 400:
            raise STTError(f"sarvam {r.status_code}: {r.text[:300]}")
        payload = r.json()

    raw = (payload.get("transcript") or payload.get("text") or "").strip()
    fixed: Corrected = correct(raw, entities or [])
    ms = int((time.monotonic() - started) * 1000)
    if fixed.changed:
        log.info("stt repaired %s", [(c.original, c.replacement) for c in fixed.corrections])
    return Transcript(raw=raw, text=fixed.text,
                      language=payload.get("language_code") or language,
                      ms=ms, corrections=fixed.corrections)
