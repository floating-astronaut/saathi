"""TTS (PR-8): chunking, WAV concat, phrase cache, the voice trigger policy, and
that voice is strictly additive to — never a gate on — the text reply."""
import base64
import io
import typing
import wave

import pytest

from saathi import usage
from saathi.config import settings
from saathi.core.context import MessageContext
from saathi.speech import tts, tts_speaker


def _wav(frames: bytes = b"\x00\x00" * 100) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(22050)
        w.writeframes(frames)
    return buf.getvalue()


# --- pure helpers ----------------------------------------------------------

def test_chunk_splits_long_text_on_sentence_boundaries():
    text = "Ek baat. " * 50  # ~450 chars
    parts = tts._chunk(text, 100)
    assert all(len(p) <= 100 for p in parts)
    assert "".join(parts.copy()).replace(" ", "") != ""  # nothing dropped to empty


def test_chunk_short_text_is_one_piece():
    assert tts._chunk("Namaste", 1200) == ["Namaste"]
    assert tts._chunk("   ", 1200) == []


def test_concat_wavs_sums_frames():
    one = _wav(b"\x01\x00" * 100)
    joined = tts._concat_wavs([one, one])
    with wave.open(io.BytesIO(joined), "rb") as r:
        assert r.getnframes() == 200
        assert r.getframerate() == 22050


# --- synthesize_ogg + phrase cache -----------------------------------------

class FakeProvider:
    name = "fake"

    def __init__(self):
        self.calls = 0

    async def synthesize(self, text, lang):
        self.calls += 1
        return _wav(), "req-1"


async def test_synthesize_ogg_caches_fixed_phrases(monkeypatch):
    monkeypatch.setattr(tts, "wav_to_ogg_opus", lambda wav, bitrate="48k": _fake_ogg())
    tts._CACHE.clear()
    provider = FakeProvider()

    first = await tts.synthesize_ogg("Shabaash! Ho gaya.", "hi-IN", provider=provider)
    second = await tts.synthesize_ogg("Shabaash! Ho gaya.", "hi-IN", provider=provider)

    assert provider.calls == 1        # second served from the phrase bank
    assert first.cached is False and second.cached is True
    assert second.ms == 0


async def _fake_ogg():
    return b"OGG"


# --- the trigger policy (should_voice) -------------------------------------

def _ctx(**kw):
    base = {"conn": None, "transport": None, "channel": "whatsapp", "handle": "h",
            "msg": {}, "user_id": 1, "display_name": None, "tz": "Asia/Kolkata",
            "voice_pref": "auto", "onboarding": "done", "kind": "audio"}
    base.update(kw)
    return MessageContext(**base)


def test_should_voice_off_by_default(monkeypatch):
    monkeypatch.setattr(settings, "saathi_tts_enabled", False)
    assert _ctx().should_voice() is False


def test_should_voice_auto_is_voice_in_voice_out(monkeypatch):
    monkeypatch.setattr(settings, "saathi_tts_enabled", True)
    assert _ctx(kind="audio").should_voice() is True     # spoke -> speak back
    assert _ctx(kind="text").should_voice() is False     # typed -> stay text


def test_should_voice_respects_preference(monkeypatch):
    monkeypatch.setattr(settings, "saathi_tts_enabled", True)
    assert _ctx(kind="text", voice_pref="always").should_voice() is True
    assert _ctx(kind="audio", voice_pref="never").should_voice() is False


def test_should_voice_never_during_onboarding(monkeypatch):
    monkeypatch.setattr(settings, "saathi_tts_enabled", True)
    assert _ctx(kind="audio", onboarding="lang").should_voice() is False


# --- ctx.reply: voice is additive and never breaks the turn ----------------

class RecordingTransport:
    def __init__(self, voice_raises=False):
        self.texts, self.voices, self.voice_raises = [], [], voice_raises

    def format_text(self, t):
        return t

    async def send_text(self, conn, user_id, handle, text):
        self.texts.append(text)
        return "mid-text"

    async def send_voice(self, conn, user_id, handle, text, lang, *, wa_message_id=None):
        if self.voice_raises:
            raise RuntimeError("tts exploded")
        self.voices.append((text, lang))
        return "mid-voice"


async def test_reply_sends_voice_when_triggered(monkeypatch):
    monkeypatch.setattr(settings, "saathi_tts_enabled", True)
    t = RecordingTransport()
    ctx = _ctx(transport=t, kind="audio", lang="hi")
    await ctx.reply("Aaj kaisa mahsoos ho raha hai?")
    assert t.texts == ["Aaj kaisa mahsoos ho raha hai?"]
    assert t.voices == [("Aaj kaisa mahsoos ho raha hai?", "hi-IN")]


async def test_reply_text_only_when_disabled(monkeypatch):
    monkeypatch.setattr(settings, "saathi_tts_enabled", False)
    t = RecordingTransport()
    await _ctx(transport=t, kind="audio").reply("hi")
    assert t.texts == ["hi"] and t.voices == []


async def test_reply_survives_voice_failure(monkeypatch):
    monkeypatch.setattr(settings, "saathi_tts_enabled", True)
    t = RecordingTransport(voice_raises=True)
    mid = await _ctx(transport=t, kind="audio").reply("hi")
    assert mid == "mid-text"          # text reply still returned; no exception


# --- ledger cost -----------------------------------------------------------

def test_tts_cost_is_per_character_estimate():
    assert usage.sarvam_tts_cost_paise(1000, paise_per_1k=150) == 150
    assert usage.sarvam_tts_cost_paise(0, paise_per_1k=150) == 0
    with pytest.raises(ValueError):
        usage.sarvam_tts_cost_paise(-1, paise_per_1k=150)


# --- per-language voice + v3 request (VOICE-1) -----------------------------

def test_speaker_is_per_language():
    assert tts_speaker("hi-IN", "fallback") == "ritu"
    assert tts_speaker("gu-IN", "fallback") == "priya"
    assert tts_speaker("ml-IN", "fallback") == "kavitha"
    assert tts_speaker("en-IN", "fallback") == "neha"
    assert tts_speaker("ta-IN", "fallback") == "fallback"   # unmapped -> default


class _Resp:
    status_code = 200
    def __init__(self, payload): self._p = payload
    def json(self): return self._p


class _Client:
    """Captures the request body SarvamTTS sends."""
    captured: typing.ClassVar[dict] = {}
    def __init__(self, *a, **k): pass
    async def __aenter__(self): return self
    async def __aexit__(self, *a): return False
    async def post(self, url, headers=None, json=None):
        _Client.captured = json
        return _Resp({"audios": [base64.b64encode(_wav()).decode()], "request_id": "r"})


async def test_synthesize_sends_v3_preprocessing_and_language_voice(monkeypatch):
    monkeypatch.setattr(settings, "sarvam_api_key", "test-key")
    monkeypatch.setattr(tts.httpx, "AsyncClient", _Client)
    await tts.SarvamTTS().synthesize("namaste", "gu-IN")
    sent = _Client.captured
    assert sent["model"] == "bulbul:v3"
    assert sent["speaker"] == "priya"              # Gujarati voice, not the global default
    assert sent["speech_sample_rate"] == 48000
    assert sent["enable_preprocessing"] is True
    assert sent["target_language_code"] == "gu-IN"
