"""Redaction, and the rules about what may ever become training data.

The design principle: **privacy holds by construction, not by policy.** We do
not store conversations and redact them later — we never write the sensitive
thing in the first place. If that makes the corpus smaller and the training
weaker, that is the accepted trade (operator decision, 2026-07-26).

Three rules, in order of how much they protect:

1. **We never train on transcripts.** The corpus is *derived*: token pairs and
   structured extractions. `"bomlodipin" -> "Amlodipine"` is a fact about how
   Indian speech is mis-transcribed. `"roz subah Priya ko phone karna hai"` is a
   fact about a person. Only the first kind is ever written.

2. **Person and place names are never trainable.** A medicine or brand name is
   shared vocabulary — thousands of people say "Amlodipine". A family member's
   name, a doctor's name, a neighbourhood: those identify. `TRAINABLE_KINDS`
   encodes this and `is_trainable_entity` is the only gate.

3. **k-anonymity on export.** Even a permitted pair is only exported once at
   least `K_ANON` *distinct users* have produced it. Anything unique to one
   person never leaves the box, however innocuous it looks. This is what turns
   "a medicine this user takes" (health data about them) into "a word Indian ASR
   mishears" (a property of the language).

Consent is separate and opt-in. Under DPDP, improving the model is a *different
purpose* from providing the service, so it cannot ride on the service consent —
especially when the vocabulary is health-adjacent.
"""
from __future__ import annotations

import re
import unicodedata

#: Entity kinds whose *values* are shared vocabulary rather than identifiers.
#: Deliberately excludes `person`, `place` and `other`.
TRAINABLE_KINDS = frozenset({"medicine", "brand"})

#: A derived pair must come from at least this many distinct users before it can
#: leave the box. Small enough to be useful, large enough that nothing unique to
#: one person is ever exported.
K_ANON = 5

# --- redaction ---------------------------------------------------------------

_PHONE = re.compile(r"(?:\+?\d[\d\-\s]{7,}\d)")
_EMAIL = re.compile(r"[\w.\-+]+@[\w\-]+\.[\w.\-]+")
_URL = re.compile(r"https?://\S+|www\.\S+")
# Long digit runs: OTPs, account numbers, PINs, Aadhaar-shaped strings.
_DIGITS = re.compile(r"\b\d{4,}\b")
_MONEY = re.compile(r"(?:₹|rs\.?|inr)\s?\d[\d,.]*", re.I)


def redact(text: str) -> str:
    """Strip the identifiers that appear in ordinary conversation.

    This is a *safety net* for anything that reaches a log or a sample, not the
    primary control — the primary control is not writing free text at all.
    Redaction is not anonymisation and is never treated as such here.
    """
    if not text:
        return ""
    t = unicodedata.normalize("NFKC", text)
    t = _URL.sub("[url]", t)
    t = _EMAIL.sub("[email]", t)
    t = _PHONE.sub("[phone]", t)
    t = _MONEY.sub("[amount]", t)
    t = _DIGITS.sub("[number]", t)
    return t.strip()


def is_trainable_entity(kind: str) -> bool:
    """Whether an entity of this kind may contribute a training pair at all.

    Person and place names never may — no threshold, no consent flag, no
    override. They identify, and a shared-vocabulary corpus has no use for them.
    """
    return kind in TRAINABLE_KINDS


_TOKEN = re.compile(r"^[A-Za-z][A-Za-z0-9\-]{2,39}$")


def is_safe_token(token: str) -> bool:
    """A single Latin word, no digits-only, no punctuation, no whitespace.

    Anything that is not one plain word is rejected rather than cleaned: a
    cleaner that tries to rescue a messy string is exactly where PII leaks in.
    """
    return bool(token) and bool(_TOKEN.match(token))


def scrub_slots(slots: dict) -> dict:
    """Reduce an extracted slot set to its *shape*, discarding the content.

    We want to learn "an utterance with a part-of-day plus a fractional Hindi
    clock word yields HH:MM" — not what this person takes or when. So values are
    replaced with types, except the time itself, which is the thing being learned
    and carries no identity on its own.
    """
    out: dict = {}
    for k, v in (slots or {}).items():
        if k == "time_24h" and isinstance(v, str) and re.fullmatch(r"\d{2}:\d{2}", v):
            out[k] = v
        elif k == "recurrence" and isinstance(v, str):
            out[k] = v.split(":", 1)[0]          # weekly:mon -> weekly
        elif isinstance(v, str):
            out[k] = f"<{k}>"                     # title etc. -> shape only
    return out
