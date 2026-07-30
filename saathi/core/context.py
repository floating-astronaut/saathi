"""Everything a handler needs, assembled once.

Passing a context object rather than a widening parameter list is what keeps
handlers independent: a new capability reads what it needs and ignores the rest,
without changing any signature that other handlers depend on.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from ..config import settings

log = logging.getLogger("saathi.core.context")


@dataclass
class MessageContext:
    conn: Any
    transport: Any
    channel: str
    handle: str                      # channel-native id of the sender
    msg: dict                        # raw inbound payload
    user_id: int
    display_name: str | None
    tz: str
    voice_pref: str
    onboarding: str
    #: The script the user chose, not the one they happen to type in. Reading
    #: and typing diverge for this audience: someone who reads Devanagari
    #: comfortably may still type Latin because that is the keyboard they have.
    lang: str = "hi"
    #: Where the account stands against its allowance: active | exhausted | paid.
    #: Resolved once in the pipeline, like `onboarding`, because `Handler.matches`
    #: is **synchronous** — an async matcher returns a truthy coroutine and would
    #: put every user behind the paywall.
    account_status: str = "active"
    wa_message_id: str | None = None
    kind: str = "text"               # text | audio | image | document | interactive
    text: str = ""                   # resolved text (transcribed if voice)
    transcript: Any = None
    conversation_id: int | None = None
    message_id: int | None = None
    #: Did the user author this, or is it forwarded/lifted from media?
    provenance: str = "typed"
    meta: dict = field(default_factory=dict)

    @property
    def button_id(self) -> str:
        """The payload behind a tap, whichever of the two shapes WhatsApp used.

        Interactive messages we compose ourselves carry it at
        `interactive.button_reply.id`; a **list** selection (the language picker,
        LANG-2) at `interactive.list_reply.id`. **Template** quick-replies arrive
        as a different message type entirely — `button.payload` — which was never
        read, so every reminder acknowledgement was silently dropped (PR-4b).
        """
        inter = self.msg.get("interactive") or {}
        reply = inter.get("button_reply") or inter.get("list_reply") or {}
        if reply.get("id"):
            return reply["id"]
        return (self.msg.get("button") or {}).get("payload", "")

    @property
    def trusted(self) -> bool:
        """False for forwarded or media-extracted text — content, not command."""
        from ..provenance import Provenance
        return Provenance(self.provenance).is_trusted

    @property
    def is_onboarded(self) -> bool:
        return self.onboarding == "done"

    def should_voice(self) -> bool:
        """Whether to also speak this reply (PR-8, D-AE).

        Policy lives here (context), mechanism in the channel. Gated by the
        master flag, then the user's stored preference, then the default trigger
        the operator chose to start with — voice-in→voice-out. Onboarding stays
        text-only so the open door stays fast (D: onboarding never calls a model;
        no reason to add TTS latency/cost to it either)."""
        if not settings.saathi_tts_enabled:
            return False
        if not self.is_onboarded:
            return False
        if self.voice_pref == "never":
            return False
        if self.voice_pref == "always":
            return True
        return self.kind == "audio"          # 'auto': voice-in -> voice-out

    def _tts_lang(self) -> str:
        """Map the user's script choice to a Sarvam language code (hi/en/gu/ml)."""
        from ..speech import sarvam_lang
        return sarvam_lang(self.lang)

    async def reply(self, text: str) -> str:
        """Send formatted text back, and — best-effort — speak it (PR-8).

        The voice note is additive to and never gates the text reply: if TTS is
        off, unsupported, capped, or fails, the text has already gone."""
        mid = await self.transport.send_text(
            self.conn, self.user_id, self.handle, self.transport.format_text(text))
        if self.should_voice():
            try:
                await self.transport.send_voice(
                    self.conn, self.user_id, self.handle, text, self._tts_lang(),
                    wa_message_id=self.wa_message_id)
            except Exception:
                log.exception("voice reply failed for user %s", self.user_id)
        return mid
