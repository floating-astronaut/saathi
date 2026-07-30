"""What a messaging channel must provide.

WhatsApp is a transport, not the product. Everything above this line — the
agent, memory, reminders, safety — is channel-agnostic; everything WhatsApp-
specific lives behind `Transport`.

The interesting part is `Capabilities`. Channels differ in ways that change
*product behaviour*, not just wire format:

  * WhatsApp has a **24-hour session window** and pre-approved templates.
    Telegram and Discord have neither — a bot can message whenever it likes.
    So "is this send allowed right now?" is a channel question, and the window
    guard must ask the transport rather than assume.
  * Button counts differ (WhatsApp 3 quick replies; Telegram far more). The
    errorless-by-default principle (PRD §6.6) says prefer buttons over free
    text where a choice is bounded — so the *number* available changes how a
    prompt should be phrased.
  * Voice notes are native on WhatsApp and Telegram, absent on SMS. A
    voice-first product degrades differently on each.

Encoding these as data rather than `if channel == "whatsapp"` scattered through
the pipeline is the whole point.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class Capabilities:
    #: Sending outside a session requires a pre-approved template (WhatsApp).
    has_session_window: bool = False
    session_window_hours: int = 0
    #: Proactive messages need pre-approval (WhatsApp templates).
    requires_templates: bool = False
    max_quick_replies: int = 0
    quick_reply_label_len: int = 20
    supports_voice_notes: bool = False
    supports_cta_url_button: bool = False
    max_text_len: int = 4096
    #: Native markup. WhatsApp uses *bold*; Telegram accepts real Markdown.
    markup: str = "plain"
    #: Can this channel carry an in-thread invoice? WhatsApp Pay, India only.
    #: False everywhere else, so a paywall on another channel refuses loudly
    #: rather than silently failing to charge.
    supports_payments: bool = False


@runtime_checkable
class Transport(Protocol):
    """One messaging channel. Implementations must be side-effect free to import."""

    channel: str
    capabilities: Capabilities

    async def send_text(self, conn, user_id: int, handle: str, text: str) -> str: ...

    async def send_voice(self, conn, user_id: int, handle: str, text: str, lang: str,
                         *, wa_message_id: str | None = None) -> str | None:
        """Speak a reply as a voice note, where the channel supports it (PR-8).

        Best-effort and additive to `send_text`: returns the message id or None
        (unsupported/disabled/failed). Default no-op — SMS has no voice notes, so
        a voice-first product degrades to text there rather than erroring."""
        return None

    async def send_buttons(self, conn, user_id: int, handle: str, body: str,
                           buttons: list[tuple[str, str]]) -> str: ...

    async def send_list(self, conn, user_id: int, handle: str, body: str,
                        button: str, rows: list[tuple[str, str]]) -> str:
        """A tappable list of choices (more than the 3 quick-reply buttons allow).

        Default falls back to buttons where a channel has no list type; a
        transport that supports neither should raise."""
        return await self.send_buttons(conn, user_id, handle, body, rows[:3])

    async def send_template(self, conn, user_id: int, handle: str, name: str,
                            lang: str, variables: list[str]) -> str: ...

    async def fetch_media(self, media_id: str, max_bytes: int) -> bytes: ...

    async def send_order_details(self, conn, user_id: int, handle: str,
                                 payload: dict) -> str:
        """Send an invoice. Only meaningful where `supports_payments` is True."""
        raise NotImplementedError(f"{self.channel} cannot carry an invoice")

    def format_text(self, text: str) -> str:
        """Render model output in this channel's native markup."""
        return text


class ChannelNotAvailable(RuntimeError):
    """Raised when a send is not permitted on this channel right now.

    On WhatsApp this means the 24-hour window has closed and only a template is
    deliverable. On a channel without a window it should never be raised.
    """


class MediaTooLarge(RuntimeError):
    """The sender's file exceeds the byte limit the caller asked for.

    `fetch_media` takes its limit as an argument rather than defaulting to one,
    so a new call site cannot inherit "no limit" by omission. Raised *instead
    of* returning bytes: a transport that could not establish the size of what
    it was downloading must refuse, because "I could not tell" and "it is small"
    are not the same answer.
    """

    def __init__(self, media_id: str, size: int | None, limit: int):
        super().__init__(
            f"media {media_id} is {size if size is not None else 'an unknown number of'} "
            f"bytes, over the {limit}-byte limit")
        self.media_id, self.size, self.limit = media_id, size, limit
