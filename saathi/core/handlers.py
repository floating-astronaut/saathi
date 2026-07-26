"""Handler chain: capabilities register themselves instead of being wired in.

The problem this solves, which is the one that breaks products at scale: a
pipeline written as `if kind == "image": ... elif text.startswith("/"): ...`
grows a branch per feature. Every capability edits the same function, the order
becomes implicit, and nobody can say what runs before what without reading all
of it.

Here a capability is an object that declares:

    priority  — lower runs first; safety-critical work claims the low numbers
    matches() — cheap, side-effect-free "is this mine?"
    handle()  — does the work, returns a result to stop the chain, or None to
                fall through to the next handler

Adding web search, weather, or a new document type is then a new module plus a
`register(...)` call — the pipeline itself never changes. Ordering is data
(`priority`), not the order somebody happened to write the branches in.

Priority bands, so the ordering stays legible as this grows:

    0-9    safety and admission   — must not be overtakeable
    10-19  onboarding             — a new user is not a general query
    20-29  deterministic commands — unambiguous, model-free
    30-49  media and modality
    50-89  specific capabilities
    90-99  the agent, as the catch-all
"""
from __future__ import annotations

import logging
from typing import Awaitable, Callable, Protocol, runtime_checkable

from .context import MessageContext

log = logging.getLogger("saathi.handlers")


@runtime_checkable
class Handler(Protocol):
    name: str
    priority: int

    def matches(self, ctx: MessageContext) -> bool: ...

    async def handle(self, ctx: MessageContext) -> dict | None: ...


_REGISTRY: list[Handler] = []


def register(handler: Handler) -> Handler:
    """Add a capability. Safe to call at import time; order is by priority."""
    if any(h.name == handler.name for h in _REGISTRY):
        raise ValueError(f"duplicate handler name {handler.name!r}")
    _REGISTRY.append(handler)
    _REGISTRY.sort(key=lambda h: h.priority)
    return handler


def registered() -> list[Handler]:
    return list(_REGISTRY)


def clear() -> None:
    """Test seam only."""
    _REGISTRY.clear()


def simple(name: str, priority: int,
           matches: Callable[[MessageContext], bool],
           handle: Callable[[MessageContext], Awaitable[dict | None]]) -> Handler:
    """Build a handler from two functions, for capabilities that need no state."""
    class _H:
        pass
    h = _H()
    h.name, h.priority = name, priority
    h.matches, h.handle = matches, handle
    return h  # type: ignore[return-value]


async def dispatch(ctx: MessageContext) -> dict:
    """Run the chain. First handler to return a result wins.

    A handler that raises is logged and skipped rather than killing the turn —
    one broken capability must not take the assistant down for a user who was
    only asking about their medicine.
    """
    for h in _REGISTRY:
        try:
            if not h.matches(ctx):
                continue
        except Exception:  # noqa: BLE001
            log.exception("handler %s: matches() raised", h.name)
            continue
        try:
            result = await h.handle(ctx)
        except Exception:  # noqa: BLE001
            log.exception("handler %s: handle() raised", h.name)
            continue
        if result is not None:
            return {"handler": h.name, **result}
    return {"handled": "nothing"}
