"""Scoring primitives for the STT eval — pure, no I/O, no audio, no network.

Two kinds of number:

  * **entity_present** — the one that matters (PRD §15). Did a token that had to
    survive transcription actually survive? It reuses the *exact* normalisation
    and fuzzy threshold the product uses to resolve entities
    (`saathi/speech/correct.py`), so the eval never reports accuracy the pipeline
    could not itself deliver.
  * **wer / cer** — diagnostics only. A transcript can be 92% word-accurate and
    still have the medicine name wrong, so these never gate pass/fail; they just
    tell you *where* the errors landed.
"""
from __future__ import annotations

import re

# Reuse the product's matching, not a lookalike. If correct.py retunes its
# threshold or normalisation, the eval moves with it by construction.
from ..speech.correct import THRESHOLD, _norm, _similar

__all__ = ["THRESHOLD", "cer", "entity_present", "wer"]


def _words(s: str) -> list[str]:
    return re.findall(r"\w+", s.lower())


def _levenshtein(a: list, b: list) -> int:
    """Edit distance between two sequences (of tokens or characters)."""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cost = 0 if ca == cb else 1
            cur.append(min(prev[j] + 1, cur[-1] + 1, prev[j - 1] + cost))
        prev = cur
    return prev[-1]


def wer(reference: str, hypothesis: str) -> float:
    """Word error rate. Diagnostic only — see module docstring and PRD §15.

    An empty reference scores 0.0 against an empty hypothesis and 1.0 against a
    non-empty one (the model invented words), rather than dividing by zero.
    """
    ref, hyp = _words(reference), _words(hypothesis)
    if not ref:
        return 0.0 if not hyp else 1.0
    return _levenshtein(ref, hyp) / len(ref)


def cer(reference: str, hypothesis: str) -> float:
    """Character error rate over NFKC-folded, lowercased text. Diagnostic only."""
    ref = list(_norm(reference))
    hyp = list(_norm(hypothesis))
    if not ref:
        return 0.0 if not hyp else 1.0
    return _levenshtein(ref, hyp) / len(ref)


def _word_present(word: str, text_tokens: list[str], threshold: float) -> bool:
    nw = _norm(word)
    if not nw:
        # Punctuation-only fragment of a multi-word entity — nothing to match.
        return True
    for tok in text_tokens:
        nt = _norm(tok)
        if not nt:
            continue
        # A number must land exactly. "8 baje" heard as "9 baje" is a wrong time,
        # and fuzzy string similarity would wave "8"/"9" through (ratio 0.0 but a
        # one-char slip elsewhere could still pass) — so digits get an == gate.
        if nw.isdigit() or nt.isdigit():
            if nw == nt:
                return True
            continue
        if _similar(word, tok) >= threshold:
            return True
    return False


def entity_present(entity: str, text: str, threshold: float = THRESHOLD) -> bool:
    """Did `entity` survive into `text`?

    Uses the pipeline's own fuzzy threshold (`correct.THRESHOLD`, 0.78) over
    NFKC-folded tokens. A multi-word entity ("Dr Mehta", "aath baje") counts as
    present only when *every* significant word survives — the manifest author
    lists exactly the tokens that must be preserved, so if only the number
    matters they write "8", and if the whole phrase matters they write it whole.
    """
    words = [w for w in re.split(r"\s+", entity.strip()) if w]
    if not words:
        return False
    tokens = [t for t in re.split(r"\s+", text) if t]
    return all(_word_present(w, tokens, threshold) for w in words)
