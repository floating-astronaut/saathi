"""Inline commands — deterministic, pre-LLM, free.

Two reasons these exist, and the second matters more:

1. **Cost and latency.** "stop", "help", "delete everything" are unambiguous.
   Routing them through a model adds a second of latency, a fraction of a rupee,
   and a chance of getting them wrong. A regex cannot mis-handle "stop".

2. **They must work when the model is broken.** If Bedrock is down, the agent
   is down — but a user asking to stop, or to delete their data, must still be
   answered. A DPDP erasure request that depends on an LLM being available is
   not a real erasure mechanism.

Slash forms (`/help`) are supported because operators and testers expect them,
but they are not the intended UX: an elder types "band karo", not "/stop". Both
resolve to the same command.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from enum import Enum


class Command(str, Enum):
    START = "start"
    HELP = "help"
    STOP = "stop"           # pause messages, keep data
    RESUME = "resume"
    DELETE_ALL = "delete_all"
    WHAT_YOU_KNOW = "what_you_know"
    CLEAR_CHAT = "clear_chat"


@dataclass(frozen=True)
class Parsed:
    command: Command | None
    matched: str | None = None


# Natural phrasings first — these are what people actually send. Hindi in Latin
# script and English, because that is how the users write.
_PATTERNS: list[tuple[Command, list[str]]] = [
    (Command.DELETE_ALL, [
        r"\bforget everything\b", r"\bdelete everything\b", r"\bdelete my (data|account)\b",
        r"sab kuch bhool ja", r"sab kuchh bhul ja", r"mera data delete",
        r"\berase everything\b",
    ]),
    (Command.CLEAR_CHAT, [
        r"\bclear (this )?chat\b", r"\bdelete (this )?(chat|conversation)\b",
        r"chat (saaf|clear) kar", r"baat.chit mita",
    ]),
    (Command.WHAT_YOU_KNOW, [
        r"what do you know about me", r"\bwhat have you (stored|remembered)\b",
        r"mere baare mein kya (jaante|jaanti|pata)", r"kya kya yaad hai",
    ]),
    (Command.STOP, [
        r"^\s*stop\s*$", r"\bstop messaging\b", r"\bunsubscribe\b",
        r"\bband kar", r"message mat bhej", r"\bbandh kar", r"\bbandh?\s+kar",
    ]),
    (Command.RESUME, [
        r"^\s*(resume|start again)\s*$", r"\bphir se shuru\b", r"\bchalu kar\b",
    ]),
    (Command.HELP, [
        r"^\s*help\s*$", r"\bwhat can you do\b", r"\baap kya kar sakt", r"^\s*madad\s*$",
    ]),
    (Command.START, [r"^\s*(start|hi|hello|namaste|namaskar)\s*[!.]?\s*$"]),
]

_COMPILED = [(c, [re.compile(p, re.I) for p in pats]) for c, pats in _PATTERNS]

_SLASH = {
    "/start": Command.START, "/help": Command.HELP, "/stop": Command.STOP,
    "/resume": Command.RESUME, "/delete": Command.DELETE_ALL,
    "/forget": Command.DELETE_ALL, "/whatyouknow": Command.WHAT_YOU_KNOW,
    "/clear": Command.CLEAR_CHAT,
}


def parse(text: str) -> Parsed:
    """Return the command this message unambiguously is, or nothing.

    Deliberately conservative. "Can you help me set a reminder" is a task for the
    agent, not the HELP command — so HELP only matches a bare "help", never any
    sentence containing the word.
    """
    if not text:
        return Parsed(None)
    t = unicodedata.normalize("NFKC", text).strip()
    low = t.lower()

    first = low.split()[0] if low.split() else ""
    if first in _SLASH:
        return Parsed(_SLASH[first], first)

    for cmd, pats in _COMPILED:
        for p in pats:
            m = p.search(low)
            if m:
                return Parsed(cmd, m.group(0).strip())
    return Parsed(None)
