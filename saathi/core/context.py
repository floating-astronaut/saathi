"""Everything a handler needs, assembled once.

Passing a context object rather than a widening parameter list is what keeps
handlers independent: a new capability reads what it needs and ignores the rest,
without changing any signature that other handlers depend on.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


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
        return ((self.msg.get("interactive") or {}).get("button_reply") or {}).get("id", "")

    @property
    def trusted(self) -> bool:
        """False for forwarded or media-extracted text — content, not command."""
        from ..provenance import Provenance
        return Provenance(self.provenance).is_trusted

    @property
    def is_onboarded(self) -> bool:
        return self.onboarding == "done"

    async def reply(self, text: str) -> str:
        """Send formatted text back on whatever channel this arrived from."""
        return await self.transport.send_text(
            self.conn, self.user_id, self.handle, self.transport.format_text(text))
