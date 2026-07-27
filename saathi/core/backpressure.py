"""Admission slots for work that costs more than a reply.

The webhook acks Meta immediately and detaches the real work with
`asyncio.create_task`, which means the number of messages being processed at
once is chosen by whoever is sending them. That is fine for text. It is not
fine for anything that downloads megabytes, parses them, or forks a renderer:
on a 2 vCPU / 8 GiB box the reminder worker and the safety classifier share
those resources, and this product's worst failure is a missed dose.

A `Gate` is the smallest thing that fixes it: a counter with a ceiling.

**It refuses rather than queues.** A queue in front of CPU-bound work is the
same unbounded growth wearing a hat — it accepts everything, holds every blob
in memory while it waits, and delivers an answer minutes after the person gave
up. Refusing is honest, and the caller can say so kindly. The cost is that a
legitimate second document arrives at a busy moment and is asked to try again;
that is a message an elder can act on, unlike silence.

**It is per-process and in-memory**, which is exactly as far as it can be
trusted: it bounds what `saathi-web` will do to itself. It is not a rate limit
and it is not shared with the worker. See `PROD_READINESS.md` PR-26.

No lock is taken. Every hold is acquired and released on the event loop thread,
so the increment cannot interleave; a gate used from a thread would need one.
"""
from __future__ import annotations

import contextlib
import logging

log = logging.getLogger("saathi.backpressure")


class Busy(RuntimeError):
    """No slot was free. The caller must refuse, not wait."""

    def __init__(self, gate: str, limit: int):
        super().__init__(f"{gate} is at its limit of {limit}")
        self.gate, self.limit = gate, limit


class Gate:
    def __init__(self, name: str, limit: int):
        # Fail loudly on a misconfigured ceiling. A gate with limit 0 or a
        # negative one would refuse everything; one built from a bad string
        # would fail open on the first comparison. Neither should reach runtime.
        if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
            raise ValueError(f"gate {name!r} needs a positive integer limit, got {limit!r}")
        self.name, self.limit = name, limit
        self._held = 0

    @property
    def in_flight(self) -> int:
        return self._held

    @contextlib.contextmanager
    def hold(self):
        """Occupy a slot for the duration of the block, or raise `Busy`."""
        if self._held >= self.limit:
            log.warning("gate %s full (%s in flight); refusing", self.name, self._held)
            raise Busy(self.name, self.limit)
        self._held += 1
        try:
            yield
        finally:
            self._held -= 1
