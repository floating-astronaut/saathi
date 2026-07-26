"""ffmpeg transcode, both directions (PRD §9).

Inbound  : WhatsApp OGG/Opus -> WAV 16k mono PCM, which is what Sarvam wants.
Outbound : WAV/PCM -> OGG/Opus, or WhatsApp renders a file attachment instead
           of a voice-note bubble.
ffmpeg is in the hot path both ways, so both functions are subprocess-bounded.
"""
from __future__ import annotations

import asyncio


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
    """Inbound voice note -> 16 kHz mono PCM WAV for STT."""
    return await _run(["ffmpeg", "-hide_banner", "-loglevel", "error",
                       "-i", "pipe:0", "-ar", "16000", "-ac", "1",
                       "-c:a", "pcm_s16le", "-f", "wav", "pipe:1"], ogg)


async def wav_to_ogg_opus(wav: bytes, bitrate: str = "32k") -> bytes:
    """Outbound TTS -> OGG/Opus so it appears as a voice note with a waveform."""
    return await _run(["ffmpeg", "-hide_banner", "-loglevel", "error",
                       "-i", "pipe:0", "-c:a", "libopus", "-b:a", bitrate,
                       "-f", "ogg", "pipe:1"], wav)
