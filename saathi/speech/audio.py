"""ffmpeg transcode, both directions (PRD §9).

Inbound  : WhatsApp OGG/Opus -> WAV 16k mono PCM, which is what Sarvam wants.
Outbound : WAV/PCM -> OGG/Opus, or WhatsApp renders a file attachment instead
           of a voice-note bubble.
ffmpeg is in the hot path both ways, so both functions are subprocess-bounded.
"""
from __future__ import annotations

import asyncio
import os
import pathlib
import tempfile


class TranscodeError(RuntimeError):
    pass


async def _run(args: list[str], data: bytes, timeout: float = 30.0) -> bytes:
    proc = await asyncio.create_subprocess_exec(
        *args, stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    try:
        out, err = await asyncio.wait_for(proc.communicate(data), timeout)
    except asyncio.TimeoutError as exc:
        proc.kill()
        raise TranscodeError("ffmpeg timed out") from exc
    if proc.returncode != 0:
        raise TranscodeError(err.decode()[-400:])
    return out


async def ogg_to_wav16k(ogg: bytes) -> bytes:
    """Inbound voice note -> 16 kHz mono PCM WAV for STT.

    Writes to a temp file rather than stdout on purpose. WAV stores its length
    in the RIFF and data chunk headers, and ffmpeg cannot seek backwards on a
    pipe to fill them in — it emits the 0xFFFFFFFF streaming placeholder
    instead. Sarvam reads that as a near-infinite duration and rejects the file
    with "audio exceeds the maximum limit of 30 seconds", which is how this
    surfaced: every real voice note failed while `ffmpeg -version` looked fine.
    """
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        path = tmp.name
    try:
        await _run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                    "-i", "pipe:0", "-ar", "16000", "-ac", "1",
                    "-c:a", "pcm_s16le", path], ogg)
        return pathlib.Path(path).read_bytes()
    finally:
        os.unlink(path)


async def wav_to_ogg_opus(wav: bytes, bitrate: str = "48k") -> bytes:
    """Outbound TTS -> OGG/Opus so it appears as a voice note with a waveform.

    Quality (VOICE-1): resample to 48 kHz with soxr (Opus's native rate — a
    non-48k input otherwise gets a rough internal resample that sounded muddy),
    mono, and `-application audio` rather than the default so a warm companion
    voice is not degraded like a low-bitrate phone call. With v3 already emitting
    48 kHz the resample is a passthrough; it stays for robustness if the rate
    ever changes.
    """
    return await _run(["ffmpeg", "-hide_banner", "-loglevel", "error",
                       "-i", "pipe:0",
                       "-af", "aresample=48000:resampler=soxr:precision=28",
                       "-ac", "1", "-c:a", "libopus", "-b:a", bitrate,
                       "-application", "audio", "-f", "ogg", "pipe:1"], wav)
