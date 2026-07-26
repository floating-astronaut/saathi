"""WhatsApp 24-hour customer-service window.

Plan G2. A user message opens a 24-hour window; inside it, free-form and
interactive messages are unrestricted and free. Outside it, only pre-approved
templates are deliverable — and sending free-form anyway fails *silently enough*
that you find out from a user, not a dashboard.

So this is not a convention. `assert_can_send` is a hard gate that every send
path must pass through, and `choose_channel` is the only sanctioned way to
decide free-form vs template.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum

WINDOW = timedelta(hours=24)


class Channel(str, Enum):
    FREEFORM = "freeform"   # free, unrestricted, inside the window
    TEMPLATE = "template"   # pre-approved, costs money, works outside


class WindowClosed(RuntimeError):
    """Raised when a free-form send is attempted outside the 24-hour window."""


@dataclass(frozen=True)
class WindowState:
    user_id: int
    window_expires_at: datetime | None

    @property
    def is_open(self) -> bool:
        if self.window_expires_at is None:
            return False
        return self.window_expires_at > datetime.now(timezone.utc)

    @property
    def closes_in(self) -> timedelta | None:
        if not self.is_open:
            return None
        return self.window_expires_at - datetime.now(timezone.utc)


async def touch(conn, user_id: int, at: datetime | None = None) -> datetime:
    """Record an inbound message and (re)open the window. Returns new expiry.

    Called on every inbound webhook, before anything else. The timer resets on
    every user message, so this is an unconditional upsert.
    """
    at = at or datetime.now(timezone.utc)
    expires = at + WINDOW
    await conn.execute(
        """
        insert into sessions (user_id, last_inbound_at, window_expires_at, updated_at)
        values (%s, %s, %s, now())
        on conflict (user_id) do update
           set last_inbound_at   = excluded.last_inbound_at,
               window_expires_at = excluded.window_expires_at,
               updated_at        = now()
        """,
        (user_id, at, expires),
    )
    return expires


async def get(conn, user_id: int) -> WindowState:
    row = await (await conn.execute(
        "select window_expires_at from sessions where user_id = %s", (user_id,)
    )).fetchone()
    return WindowState(user_id=user_id, window_expires_at=row[0] if row else None)


async def choose_channel(conn, user_id: int) -> Channel:
    """The only sanctioned way to decide how to reach a user."""
    return Channel.FREEFORM if (await get(conn, user_id)).is_open else Channel.TEMPLATE


async def assert_can_send(conn, user_id: int, channel: Channel) -> None:
    """Hard gate. Call immediately before handing a payload to the Cloud API.

    Templates are always deliverable. Free-form is only deliverable inside the
    window — and we refuse locally rather than discovering it from Meta.
    """
    if channel is Channel.TEMPLATE:
        return
    state = await get(conn, user_id)
    if not state.is_open:
        raise WindowClosed(
            f"user {user_id}: 24h window closed "
            f"(expired {state.window_expires_at}); send a template instead"
        )
