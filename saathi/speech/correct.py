"""Entity correction: repair ASR output against what we know about the user.

PRD §10 and risk R1. ASR reliably mangles exactly the words that matter —
medicine names, people, places — because they are rare tokens a general model
has never seen. A transcript can be 92% word-accurate and still have the
medicine name wrong, which is the only error that matters (§15).

Two stages, cheapest first:

  1. **Deterministic fuzzy match** against the user's own entities. No model
     call, no latency, no cost, and unit-testable. "Emlodipin" -> "Amlodipine".
     This catches the common case, because ASR errors on a known rare word are
     usually near-misses rather than wild ones.
  2. An LLM repair pass, only for what stage 1 could not resolve. Not
     implemented here yet — stage 1 should be measured first, so we know what
     it actually leaves behind rather than guessing.

The compounding property is the point: the longer someone uses the product, the
more entities we hold, and the better it hears them. That is a retention
mechanic, not just an accuracy fix.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher

# Below this, a "correction" is more likely to be a different word than a
# mis-hearing. Tuned conservatively: silently swapping one real drug name for
# another is far worse than leaving a wrong transcript for the read-back to catch.
THRESHOLD = 0.78

# Never treat these as candidates for correction, however close they look.
_COMMON = {
    "hai", "hain", "ka", "ki", "ke", "ko", "me", "mein", "par", "se", "aur",
    "roz", "subah", "shaam", "raat", "din", "baje", "goli", "dawa", "lena",
    "the", "and", "for", "with", "take", "tablet", "morning", "night",
}


@dataclass(frozen=True)
class Correction:
    original: str
    replacement: str
    score: float


@dataclass
class Corrected:
    text: str
    corrections: list[Correction]

    @property
    def changed(self) -> bool:
        return bool(self.corrections)


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s).lower()
    return re.sub(r"[^a-z0-9]", "", s)


def _similar(a: str, b: str) -> float:
    return SequenceMatcher(None, _norm(a), _norm(b)).ratio()


def correct(text: str, entities: list[str]) -> Corrected:
    """Replace near-miss tokens with the user's known entities.

    Only single tokens are considered. Multi-word entities ("Dr Mehta") are
    matched on their individual significant words, which is how they actually
    get mangled -- ASR rarely drops the whole phrase, it garbles one word.
    """
    if not text or not entities:
        return Corrected(text, [])

    vocab: list[str] = []
    for e in entities:
        for word in re.findall(r"[A-Za-z][A-Za-z0-9]{2,}", e):
            if word.lower() not in _COMMON:
                vocab.append(word)
    vocab = list(dict.fromkeys(vocab))
    if not vocab:
        return Corrected(text, [])

    out, changes = [], []
    for token in re.split(r"(\W+)", text):
        if not token.strip() or not re.match(r"^[A-Za-z][A-Za-z0-9]*$", token):
            out.append(token)
            continue
        if token.lower() in _COMMON or any(token.lower() == v.lower() for v in vocab):
            out.append(token)
            continue
        best, score = None, 0.0
        for cand in vocab:
            r = _similar(token, cand)
            if r > score:
                best, score = cand, r
        if best and score >= THRESHOLD and _norm(best) != _norm(token):
            changes.append(Correction(token, best, round(score, 3)))
            out.append(best)
        else:
            out.append(token)
    return Corrected("".join(out), changes)
