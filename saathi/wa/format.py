"""Render model output as WhatsApp-safe text.

GLM-5 emits markdown (`**bold**`, `##`, `- ` bullets) despite being told not
to, and WhatsApp shows those characters literally — an elder sees asterisks and
wonders what broke. Instruction-following is the wrong tool for a deterministic
transformation, so we do it in code and stop paying prompt tokens to ask.

WhatsApp's own markup: *bold*, _italic_, ~strike~, ```mono```.
"""
from __future__ import annotations

import re

_BOLD = re.compile(r"\*\*(.+?)\*\*", re.S)      # **x** -> *x*
_HEADING = re.compile(r"^#{1,6}\s*", re.M)      # ## Heading -> Heading
_BULLET = re.compile(r"^[ \t]*[-*+]\s+", re.M)  # - item -> • item
_MDLINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")  # [t](u) -> t (u)
_BLANKS = re.compile(r"\n{3,}")


def to_whatsapp_text(text: str) -> str:
    if not text:
        return ""
    text = _BOLD.sub(r"*\1*", text)
    text = _HEADING.sub("", text)
    text = _MDLINK.sub(r"\1 (\2)", text)
    text = _BULLET.sub("• ", text)
    text = _BLANKS.sub("\n\n", text)
    return text.strip()
