"""Channel lookup. Adding Telegram is a registration, not a refactor."""
from __future__ import annotations

from .base import Transport
from .whatsapp import WhatsAppTransport

_TRANSPORTS: dict[str, Transport] = {}


def register(transport: Transport) -> None:
    _TRANSPORTS[transport.channel] = transport


def get(channel: str) -> Transport:
    try:
        return _TRANSPORTS[channel]
    except KeyError:
        raise ValueError(
            f"no transport registered for channel {channel!r}; "
            f"have {sorted(_TRANSPORTS)}") from None


def available() -> list[str]:
    return sorted(_TRANSPORTS)


register(WhatsAppTransport())
