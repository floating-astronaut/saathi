"""Deterministic pre-LLM safety classifier (PRD §12, risk R7).

Runs on every inbound message **before the model sees anything**. This is not a
prompt instruction — a prompt instruction can be argued with, and a forwarded
scam message is untrusted input that will try. Regex cannot be talked round.

Design rules:
  * Match Hindi, English and romanised Hinglish. Elders code-mix mid-sentence.
  * Prefer a false positive over a false negative. Wrongly showing an emergency
    number is a mild annoyance; missing a stroke is not.
  * Every hit short-circuits the LLM turn entirely and returns fixed copy.

Numbers used are the real Indian services:
  112    national emergency (police/fire/ambulance)
  108    state ambulance services
  14416  Tele-MANAS, Government of India mental-health helpline
  1800-599-0019  KIRAN mental-health helpline
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from enum import Enum


class Trigger(str, Enum):
    MEDICAL_EMERGENCY = "medical_emergency"
    SELF_HARM = "self_harm"
    HYPOGLYCEMIA = "hypoglycemia"
    MEDICAL_ADVICE = "medical_advice"
    SCAM = "scam"


@dataclass(frozen=True)
class Verdict:
    trigger: Trigger | None
    matched: str | None = None
    reply: str | None = None

    @property
    def blocks_llm(self) -> bool:
        # Medical-advice requests still need a warm human-sounding decline, but
        # they must not reach the tool loop; emergencies bypass everything.
        return self.trigger is not None


# --- patterns ---------------------------------------------------------------
# Written as alternations of whole words so "gir" does not match "girna sikha".

_EMERGENCY = [
    # chest / cardiac
    r"seene? me[ni]?n? dard", r"chhati me[ni]?n? dard", r"chest pain",
    r"heart attack", r"dil ka daura",
    # breathing
    r"saans nahi aa", r"saans phool", r"saans ruk", r"can'?t breathe",
    r"cannot breathe", r"breathless", r"dam ghut",
    # fall
    # "gir gaya" means fell — but "sugar gir gaya" means blood sugar dropped,
    # which needs glucose, not an ambulance. Without these lookbehinds a
    # diabetic reporting a hypo gets sent to 112 and told to call someone,
    # while the thing that would actually help goes unsaid.
    r"(?<!sugar )(?<!bp )(?<!pressure )(?<!shakkar )gir ga(ya|yi|ye)",
    r"\bfell down\b", r"\bhad a fall\b", r"utha nahi ja",
    # stroke
    r"muh tedha", r"bolne me[ni]?n? dikkat", r"ek taraf sunn",
    r"\bstroke\b", r"\bparalysis\b", r"lakwa",
    # bleeding / unconscious
    r"bahut khoon", r"heavy bleeding", r"behosh", r"unconscious",
]

# Low blood sugar. Kept separate from MEDICAL_EMERGENCY because the correct
# first action is glucose, not an ambulance — and many users on medication
# reminders are diabetic, so this is a likely event rather than an edge case.
# Severe cases (unconscious, cannot swallow) match the emergency patterns above,
# which run first.
_HYPOGLYCEMIA = [
    r"sugar (gir|kam|low) (gaya|gayi|ho)", r"sugar low", r"low sugar",
    r"\bhypoglycemia\b", r"\bhypoglycaemia\b", r"sugar bahut kam",
    r"chakkar.{0,20}pasina", r"pasina.{0,20}chakkar",
    r"haath (kaanp|kamp).{0,20}sugar", r"sugar.{0,20}haath (kaanp|kamp)",
    r"shaky.{0,15}sweat", r"sweating.{0,15}shak",
]

_SELF_HARM = [
    r"marna chahta", r"marna chahti", r"jeene ka mann nahi", r"jeena nahi chahta",
    r"khudkushi", r"aatmhatya", r"\bsuicide\b", r"kill myself", r"end my life",
    r"khatam kar du[ni]?", r"no reason to live",
]

_MEDICAL_ADVICE = [
    r"kitni goli", r"kitne mg", r"dose kitn", r"dawa badal", r"davai badal",
    r"should i (take|stop)", r"\bincrease\b.*\bdose\b", r"\bstop taking\b",
    r"goli band kar", r"is (it|this) safe to take", r"can i take .* with",
]

_SCAM = [
    # Digital arrest: fraudsters posing as CBI/police/ED over a video call.
    # No Indian agency conducts an arrest or demands money over WhatsApp.
    r"digital arrest", r"cbi se baat", r"police video call",
    r"girftar kar l", r"parcel mein drug", r"court se warrant",
    r"\bed\b.{0,15}(notice|case)", r"money laundering case",
    r"\botp\b", r"one time password", r"\bpin\b.*(bat|share|send|de do)",
    r"\bcvv\b", r"lottery", r"lucky draw", r"\bkbc\b", r"crore jeet",
    r"account (block|band)", r"kyc update", r"click (this|is) link",
    r"paisa transfer kar", r"send money urgently",
]

_COMPILED: dict[Trigger, list[re.Pattern[str]]] = {
    Trigger.MEDICAL_EMERGENCY: [re.compile(p, re.I) for p in _EMERGENCY],
    Trigger.SELF_HARM: [re.compile(p, re.I) for p in _SELF_HARM],
    Trigger.HYPOGLYCEMIA: [re.compile(p, re.I) for p in _HYPOGLYCEMIA],
    Trigger.MEDICAL_ADVICE: [re.compile(p, re.I) for p in _MEDICAL_ADVICE],
    Trigger.SCAM: [re.compile(p, re.I) for p in _SCAM],
}

# Order matters: a message can look like several things at once, and we always
# want the most urgent reading. "seene mein dard, kitni goli lu" is an emergency.
_PRIORITY = [
    Trigger.MEDICAL_EMERGENCY,   # unconscious / chest pain / stroke wins outright
    Trigger.SELF_HARM,
    Trigger.HYPOGLYCEMIA,        # before MEDICAL_ADVICE: "sugar low" is not a dosage question
    Trigger.SCAM,
    Trigger.MEDICAL_ADVICE,
]

# --- replies ----------------------------------------------------------------
# Plain, short, no hedging, action first. Never "I am only an AI, but...".

_REPLIES = {
    Trigger.MEDICAL_EMERGENCY: (
        "Yeh emergency ho sakti hai. Abhi 112 ya 108 par call kijiye, "
        "aur ghar mein kisi ko turant bulaiye.\n\n"
        "This may be an emergency. Please call 112 or 108 now, and call "
        "someone at home to be with you."
    ),
    Trigger.SELF_HARM: (
        "Aap akele nahi hain, aur main aapki baat sun raha hoon. "
        "Kripya abhi Tele-MANAS 14416 par baat kijiye — woh 24 ghante uplabdh hain.\n\n"
        "You are not alone. Please talk to someone now: Tele-MANAS 14416, "
        "or KIRAN 1800-599-0019. Both are free and open all day and night."
    ),
    Trigger.HYPOGLYCEMIA: (
        "Abhi turant kuch meetha khaiye — cheeni, glucose, juice ya do-teen "
        "toffee. Phir 15 minute baad dobara sugar check kijiye.\n\n"
        "Agar behosh jaisa lage, bolne mein dikkat ho, ya theek na lage — 112 par "
        "call kijiye aur ghar mein kisi ko abhi bulaiye.\n\n"
        "_Eat or drink something sugary right now — sugar, glucose, juice. Check "
        "again after 15 minutes. If you feel faint, confused, or it does not "
        "improve, call 112 and get someone to come to you._"
    ),
    Trigger.MEDICAL_ADVICE: (
        "Dawa ki matra ya badlav ke baare mein main salah nahi de sakta — "
        "yeh sirf aapke doctor bata sakte hain. "
        "Main aapko dawa lene ka reminder zaroor laga sakta hoon.\n\n"
        "I can't advise on doses or changing medicines — only your doctor can. "
        "I can set a reminder for you, though."
    ),
    Trigger.SCAM: (
        "Saavdhan — yeh message dhokha ho sakta hai. "
        "Apna OTP, PIN ya bank details kisi ko mat bataiye, chahe woh bank se hone ka "
        "daava kare. Kisi link par click mat kijiye.\n\n"
        "Koi bhi asli police, CBI ya bank WhatsApp video call par giraftari ki "
        "baat nahi karta. Yeh sab jhooth hota hai.\n\n"
        "Agar paise chale gaye hain — *1930* par turant call kijiye (cyber fraud "
        "helpline), aur ghar mein kisi ko abhi bataiye.\n\n"
        "Careful — this looks like a scam. Never share your OTP, PIN or bank "
        "details, even if the caller says they are from the bank or the police. "
        "No real agency arrests anyone over a video call. If money has already "
        "gone, call 1930 immediately."
    ),
}


def _normalise(text: str) -> str:
    """Fold to a comparable form: NFKC, lowercase, collapse whitespace.

    Devanagari and Latin both survive this; it mainly kills the zero-width and
    combining-character tricks that a forwarded scam message may carry.
    """
    text = unicodedata.normalize("NFKC", text or "")
    text = "".join(ch for ch in text if not unicodedata.category(ch).startswith("Cf"))
    return re.sub(r"\s+", " ", text).strip().lower()


def classify(text: str) -> Verdict:
    """Return the most urgent trigger present, or an empty verdict."""
    norm = _normalise(text)
    if not norm:
        return Verdict(None)
    for trigger in _PRIORITY:
        for pattern in _COMPILED[trigger]:
            m = pattern.search(norm)
            if m:
                return Verdict(trigger, m.group(0), _REPLIES[trigger])
    return Verdict(None)
