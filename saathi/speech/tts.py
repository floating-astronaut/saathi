"""Text-to-speech: Saathi's reply spoken back as a WhatsApp voice note (PR-8).

PRD §9 calls TTS a commodity — the product risk is *hearing* the elder (STT),
not *speaking* to them. So this is deliberately thin: a swappable provider, a
cache for the fixed phrases, and an encode step to OGG/Opus (without which
WhatsApp renders a file attachment, not a voice bubble — see wa/client.py).

Provider is Sarvam Bulbul (`bulbul:v2`), adopted by D-AE (reversing D-S's
STT-only scope now that the usage ledger can meter it). The contract was verified
live and captured in `docs/vendor/sarvam/text-to-speech.md`.

Nothing here decides *when* to speak — that policy is `core.context.should_voice`
(voice-in→voice-out by default). This module only turns text into an OGG voice
note, and is a no-op-free failure surface: it raises on failure and the caller
(`wa.send_voice_note`) swallows it best-effort, because a voice note that failed
must never take down the text reply that already succeeded.
"""
from __future__ import annotations

import base64
import io
import logging
import re
import time
import wave
from collections import OrderedDict
from dataclasses import dataclass
from typing import Protocol

import httpx

from ..config import settings
from . import tts_speaker
from .audio import wav_to_ogg_opus

log = logging.getLogger("saathi.tts")

ENDPOINT = "https://api.sarvam.ai/text-to-speech"
#: Sarvam rejects a request with more than this many `inputs` (observed live
#: 2026-07-30: "List should have at most 3 items"). Longer replies are chunked
#: and sent in batches of this size, then all audios concatenated.
MAX_INPUTS = 3


class TTSError(RuntimeError):
    pass


@dataclass
class Speech:
    ogg: bytes            # OGG/Opus, ready for wa.upload_media
    chars: int            # characters synthesised — the ledger's durable unit
    ms: int               # synthesis latency
    request_id: str | None
    cached: bool          # served from the phrase bank (no vendor spend)


class TTSProvider(Protocol):
    name: str

    async def synthesize(self, text: str, lang: str) -> tuple[bytes, str | None]:
        """Return (WAV bytes, vendor request id) for `text`."""
        ...


def _chunk(text: str, limit: int) -> list[str]:
    """Split into <= `limit`-char pieces on sentence boundaries.

    Bulbul caps characters per input; a long reply must be split and its audios
    concatenated. Splitting on sentence enders (Latin and Devanagari danda) keeps
    prosody sane rather than cutting mid-word.
    """
    text = text.strip()
    if len(text) <= limit:
        return [text] if text else []
    parts, buf = [], ""
    for piece in re.split(r"(?<=[.!?।\n])\s+", text):
        if len(buf) + len(piece) + 1 > limit and buf:
            parts.append(buf.strip())
            buf = ""
        if len(piece) > limit:
            # A single monster sentence — hard-wrap it.
            for i in range(0, len(piece), limit):
                parts.append(piece[i:i + limit])
        else:
            buf = f"{buf} {piece}".strip()
    if buf.strip():
        parts.append(buf.strip())
    return [p for p in parts if p]


def _concat_wavs(wavs: list[bytes]) -> bytes:
    """Concatenate same-format WAV clips into one, stripping the extra headers."""
    if len(wavs) == 1:
        return wavs[0]
    with wave.open(io.BytesIO(wavs[0]), "rb") as first:
        params = first.getparams()
    out = io.BytesIO()
    with wave.open(out, "wb") as writer:
        writer.setnchannels(params.nchannels)
        writer.setsampwidth(params.sampwidth)
        writer.setframerate(params.framerate)
        for w in wavs:
            with wave.open(io.BytesIO(w), "rb") as r:
                writer.writeframes(r.readframes(r.getnframes()))
    return out.getvalue()


class SarvamTTS:
    """Sarvam Bulbul. Contract: docs/vendor/sarvam/text-to-speech.md."""

    name = "sarvam-bulbul"

    async def synthesize(self, text: str, lang: str) -> tuple[bytes, str | None]:
        if not settings.sarvam_api_key:
            raise TTSError("SARVAM_API_KEY not set")
        chunks = _chunk(text, settings.saathi_tts_max_chars)
        if not chunks:
            raise TTSError("nothing to synthesize")
        # Voice is per-language (VOICE-1): the natural speaker differs by language.
        speaker = tts_speaker(lang, settings.saathi_tts_speaker)
        audios: list[str] = []
        request_id: str | None = None
        async with httpx.AsyncClient(timeout=60) as http:
            # Sarvam caps `inputs` per request (MAX_INPUTS), so a long reply is
            # sent in batches and the resulting clips concatenated.
            for i in range(0, len(chunks), MAX_INPUTS):
                batch = chunks[i:i + MAX_INPUTS]
                r = await http.post(
                    ENDPOINT,
                    headers={"api-subscription-key": settings.sarvam_api_key},
                    json={
                        "inputs": batch,
                        "target_language_code": lang,
                        "speaker": speaker,
                        "model": settings.saathi_tts_model,
                        "speech_sample_rate": settings.saathi_tts_sample_rate,
                        "enable_preprocessing": settings.saathi_tts_enable_preprocessing,
                    })
                if r.status_code >= 400:
                    raise TTSError(f"sarvam tts {r.status_code}: {r.text[:300]}")
                data = r.json()
                audios.extend(data.get("audios") or [])
                request_id = request_id or data.get("request_id")
        if not audios:
            raise TTSError("sarvam tts returned no audio")
        wav = _concat_wavs([base64.b64decode(a) for a in audios])
        return wav, request_id


# Phrase bank: cache OGG for the fixed, repeated phrases (acks, nudges, the
# limit notices) so they are synthesised once, not per fire. Model-generated
# replies vary and rarely hit, which is fine — the point is the deterministic
# strings. In-process and bounded; a persistent cache can come later if needed.
_CACHE: OrderedDict[tuple, bytes] = OrderedDict()
_CACHE_MAX = 256


def _cache_key(provider: str, lang: str, text: str) -> tuple:
    speaker = tts_speaker(lang, settings.saathi_tts_speaker)
    return (provider, speaker, lang, " ".join(text.split()))


def _cache_get(key: tuple) -> bytes | None:
    ogg = _CACHE.get(key)
    if ogg is not None:
        _CACHE.move_to_end(key)
    return ogg


def _cache_put(key: tuple, ogg: bytes) -> None:
    _CACHE[key] = ogg
    _CACHE.move_to_end(key)
    while len(_CACHE) > _CACHE_MAX:
        _CACHE.popitem(last=False)


_default_provider: TTSProvider = SarvamTTS()


async def synthesize_ogg(text: str, lang: str,
                         provider: TTSProvider | None = None) -> Speech:
    """Text -> OGG/Opus voice note, via the phrase bank then the provider.

    Raises TTSError on failure; the caller decides whether that is fatal (it is
    not — voice is best-effort on top of a text reply that already went).
    """
    provider = provider or _default_provider
    text = (text or "").strip()
    if not text:
        raise TTSError("nothing to synthesize")

    key = _cache_key(provider.name, lang, text)
    cached = _cache_get(key)
    if cached is not None:
        return Speech(ogg=cached, chars=len(text), ms=0, request_id=None, cached=True)

    started = time.monotonic()
    wav, request_id = await provider.synthesize(text, lang)
    ogg = await wav_to_ogg_opus(wav, settings.saathi_tts_ogg_bitrate)
    ms = int((time.monotonic() - started) * 1000)
    _cache_put(key, ogg)
    return Speech(ogg=ogg, chars=len(text), ms=ms, request_id=request_id, cached=False)
