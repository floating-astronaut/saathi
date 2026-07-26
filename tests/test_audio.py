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


async def test_wav_header_has_real_lengths_not_streaming_placeholder():
    """Regression: ffmpeg writing WAV to a pipe emits 0xFFFFFFFF for both size
    fields, which Sarvam reads as a >30s file and rejects. Every inbound voice
    note failed on this while ffmpeg itself looked healthy."""
    import struct
    ogg = _tone_ogg()
    wav = await ogg_to_wav16k(ogg)
    riff = struct.unpack("<I", wav[4:8])[0]
    i = wav.find(b"data")
    data = struct.unpack("<I", wav[i + 4:i + 8])[0]
    assert riff == len(wav) - 8, f"RIFF size {riff} != {len(wav) - 8}"
    assert data not in (0, 0xFFFFFFFF), f"data chunk size is a placeholder: {data}"
    # 1s of 16kHz mono s16le == 32000 bytes of PCM
    assert 28_000 < data < 36_000, data
