"""Speech: STT (Saaras), entity correction, and TTS (Bulbul).

The one thing shared across the package and its callers is how a stored
`lang_pref` maps to a Sarvam language code — used both to tell STT what to expect
and to tell TTS what to speak. Kept here (a cheap leaf) so `stt.py` and
`core.context` import it without pulling in httpx.
"""
from __future__ import annotations

#: `lang_pref` (what the onboarding picker writes) -> Sarvam language code.
#: `hi-en` is romanised Hindi, still Hindi audio. Added gu/ml in LANG-2.
LANG_TO_SARVAM = {
    "hi": "hi-IN",
    "hi-en": "hi-IN",
    "en": "en-IN",
    "gu": "gu-IN",
    "ml": "ml-IN",
}


def sarvam_lang(lang_pref: str | None) -> str:
    """Sarvam code for a stored `lang_pref`, defaulting to Hindi."""
    return LANG_TO_SARVAM.get(lang_pref or "hi", "hi-IN")


#: Sarvam Bulbul (v3) voice per language (VOICE-1). Voices are multilingual, but
#: the natural choice differs by language — a single global voice sounds off in
#: some. Keyed by Sarvam language code (what `sarvam_lang` returns). Any code not
#: listed falls back to `settings.saathi_tts_speaker`. All are v3-roster speakers.
TTS_SPEAKER_BY_LANG = {
    "hi-IN": "ritu",     # Hindi + Hinglish
    "gu-IN": "priya",    # Gujarati
    "ml-IN": "kavitha",  # Malayalam
    "en-IN": "neha",     # English
}


def tts_speaker(sarvam_code: str, default: str) -> str:
    """Voice for a Sarvam language code, falling back to the configured default."""
    return TTS_SPEAKER_BY_LANG.get(sarvam_code, default)
