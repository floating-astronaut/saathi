"""End-to-end STT check over the real WhatsApp audio path.

Synthesises Hinglish speech, encodes it as OGG/Opus (what a WhatsApp voice note
actually is), then runs the full inbound chain:

    OGG/Opus -> ffmpeg -> WAV16k -> Saaras -> entity correction

Also answers the PRD's open question in §10 — whether Saaras supports keyword
boosting — by sending identical audio with and without the bias vocabulary and
diffing the raw transcripts. If they differ, boosting is real and is the primary
mechanism; if not, the local correction pass is doing the work.
"""
from __future__ import annotations

import asyncio
import base64
import pathlib
import re
import subprocess
import sys

import httpx

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from saathi.speech.audio import ogg_to_wav16k, wav_to_ogg_opus  # noqa: E402
from saathi.speech.correct import correct  # noqa: E402
from saathi.speech.stt import ENDPOINT, MODEL  # noqa: E402

KEY = re.search(r"^SARVAM_API_KEY=(.+)$",
                pathlib.Path("/home/ubuntu/saathi/.env").read_text(), re.M).group(1).strip()

# The words that actually matter: a drug name and a Hindi fractional time.
UTTERANCES = [
    "Roz subah aath baje Amlodipine ki goli leni hai",
    "Raat ko paune gyarah baje Clopidogrel lena hai",
    "Doctor Mehta se Apollo Nagpur mein milna hai",
]
ENTITIES = ["Amlodipine 5mg", "Clopidogrel", "Telmisartan", "Dr Mehta", "Apollo Nagpur", "Priya"]


def tts(text: str) -> bytes | None:
    """Synthesise with Sarvam TTS to get realistic Indic speech to transcribe."""
    for model, lang in (("bulbul:v2", "hi-IN"), ("bulbul:v1", "hi-IN")):
        try:
            r = httpx.post("https://api.sarvam.ai/text-to-speech",
                           headers={"api-subscription-key": KEY},
                           json={"inputs": [text], "target_language_code": lang,
                                 "model": model, "speaker": "anushka"},
                           timeout=60)
            if r.status_code < 400:
                return base64.b64decode(r.json()["audios"][0])
            print(f"    tts {model} -> {r.status_code} {r.text[:120]}")
        except Exception as exc:  # noqa: BLE001
            print(f"    tts {model} error: {type(exc).__name__}")
    return None


def stt(wav: bytes, bias: list[str] | None) -> tuple[int, str]:
    data = {"model": MODEL, "language_code": "hi-IN"}
    if bias:
        data["prompt"] = ", ".join(bias)
    r = httpx.post(ENDPOINT, headers={"api-subscription-key": KEY}, data=data,
                   files={"file": ("a.wav", wav, "audio/wav")}, timeout=60)
    if r.status_code >= 400:
        return r.status_code, r.text[:160]
    j = r.json()
    return 200, (j.get("transcript") or j.get("text") or "").strip()


async def main() -> None:
    for text in UTTERANCES:
        print(f"\nspoken: {text}")
        raw_wav = tts(text)
        if not raw_wav:
            print("  (no TTS audio — skipping)")
            continue
        # round-trip through OGG/Opus exactly as WhatsApp would deliver it
        ogg = await wav_to_ogg_opus(raw_wav)
        wav16 = await ogg_to_wav16k(ogg)
        print(f"  ogg={len(ogg)}B  wav16k={len(wav16)}B")

        code_a, plain = stt(wav16, None)
        code_b, biased = stt(wav16, ENTITIES)
        if code_a != 200 or code_b != 200:
            print(f"  STT failed: {code_a} {plain} / {code_b} {biased}")
            continue
        print(f"  raw (no bias) : {plain}")
        print(f"  raw (biased)  : {biased}")
        print(f"  boosting had an effect: {plain != biased}")
        fixed = correct(plain, ENTITIES)
        print(f"  after correct : {fixed.text}")
        if fixed.changed:
            print(f"  repairs       : {[(c.original, c.replacement, c.score) for c in fixed.corrections]}")


asyncio.run(main())
