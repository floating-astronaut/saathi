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
