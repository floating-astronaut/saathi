"""ffmpeg round trip - the real WhatsApp voice-note path, not a version check."""
import asyncio, subprocess
import pytest
from saathi.speech.audio import ogg_to_wav16k, wav_to_ogg_opus, TranscodeError


def _tone_ogg() -> bytes:
    return subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi",
         "-i", "sine=frequency=440:duration=1", "-c:a", "libopus", "-f", "ogg", "pipe:1"],
        capture_output=True, check=True).stdout


async def test_inbound_then_outbound_round_trip():
    ogg = _tone_ogg()
    wav = await ogg_to_wav16k(ogg)
    assert wav[:4] == b"RIFF" and len(wav) > 1000
    # 16 kHz mono s16le for 1s ~= 32000 bytes of PCM
    assert 25_000 < len(wav) < 45_000, len(wav)
    back = await wav_to_ogg_opus(wav)
    assert back[:4] == b"OggS", "outbound must be OGG or WhatsApp shows a file attachment"


async def test_garbage_input_raises_rather_than_returning_empty():
    with pytest.raises(TranscodeError):
        await ogg_to_wav16k(b"this is not audio")
