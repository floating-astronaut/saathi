"""Content-free paid-vendor accounting primitives (LEDGER-1).

This module is deliberately not wired into vendor calls yet.  Later slices must
reserve before a paid call and settle or release afterward; a database failure
must refuse that call rather than treating missing accounting as free spend.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Reservation:
    id: int
    state: str
    reserved_minor: int
    idempotency_key: str


class UsageCapExceeded(RuntimeError):
    """A paid call would exceed the configured account cap."""


class UsageAccountingUnavailable(RuntimeError):
    """A paid call cannot be accounted for safely in enforcement mode."""


def _json(value: dict | None) -> str:
    return json.dumps(value or {}, separators=(",", ":"), sort_keys=True)


# Sarvam published price, verified 2026-07-29: ₹30/hour for STT, charged per
# second and rounded up per request. Keep integer paise, never floats.
SARVAM_STT_PRICE_VERSION = "sarvam-2026-07-29"


def sarvam_stt_cost_paise(rounded_seconds: int) -> int:
    if rounded_seconds < 0:
        raise ValueError("rounded_seconds must be non-negative")
    return math.ceil(rounded_seconds * 30 * 100 / 3600)


def enforcement_enabled(*, enabled: bool, mode: str, account_cap_paise: int) -> bool:
    """A zero/unapproved cap can never accidentally begin refusing care."""
    return enabled and mode == "enforce" and account_cap_paise > 0


async def reserve(conn, *, idempotency_key: str, user_id: int | None,
                  account_id: int, vendor: str, service: str, operation: str,
                  reserved_minor: int, currency: str = "USD", ttl_seconds: int = 300,
                  cap_minor: int | None = None) -> Reservation | None:
    """Atomically create/reuse a held reservation; ``None`` means cap exceeded.

    The per-account transaction lock prevents two concurrent calls from both
    seeing room under the same cap.  The unique key makes a retry reuse its
    original decision instead of reserving spend twice.
    """
    if not idempotency_key or account_id < 1 or reserved_minor < 0 or ttl_seconds < 1:
        raise ValueError("invalid usage reservation")
    if cap_minor is not None and cap_minor < 0:
        raise ValueError("cap_minor must be non-negative")
    async with conn.transaction():
        locked = await (await conn.execute(
            "select pg_advisory_xact_lock(%s)", (account_id,))).fetchone()
        if locked is None:
            raise RuntimeError("usage reservation lock returned no result")
        existing = await (await conn.execute(
            """select id, state::text, reserved_minor, idempotency_key
                 from vendor_usage_reservations where idempotency_key = %s""",
            (idempotency_key,))).fetchone()
        if existing:
            return Reservation(*existing)
        await conn.execute(
            """update vendor_usage_reservations set state = 'expired'
                 where account_id = %s and state = 'held' and expires_at <= now()""",
            (account_id,))
        if cap_minor is not None:
            used = await (await conn.execute(
                """select coalesce(sum(case when state = 'held' then reserved_minor
                                               else actual_minor end), 0)
                     from vendor_usage_reservations
                    where account_id = %s and currency = %s
                      and state in ('held', 'settled')""",
                (account_id, currency))).fetchone()
            if used is None:
                raise RuntimeError("usage reservation aggregate returned no result")
            if int(used[0]) + reserved_minor > cap_minor:
                return None
        row = await (await conn.execute(
            """insert into vendor_usage_reservations
                    (idempotency_key, user_id, account_id, vendor, service, operation,
                     currency, reserved_minor, expires_at)
                 values (%s, %s, %s, %s, %s, %s, %s, %s,
                         now() + (%s * interval '1 second'))
                 returning id, state::text, reserved_minor, idempotency_key""",
            (idempotency_key, user_id, account_id, vendor, service, operation, currency,
             reserved_minor, ttl_seconds))).fetchone()
        if row is None:
            raise RuntimeError("usage reservation insert returned no result")
        return Reservation(*row)


async def record_event(conn, *, vendor: str, service: str, operation: str,
                       status: str, user_id: int | None = None,
                       account_id: int | None = None, reservation_id: int | None = None,
                       model: str | None = None, request_id: str | None = None,
                       units: dict | None = None, cost: dict | None = None,
                       cost_source: str = "unknown",
                       metadata: dict | None = None, latency_ms: int | None = None,
                       error_code: str | None = None) -> int | None:
    """Append one content-free event; duplicate vendor request ids are harmless."""
    if latency_ms is not None and latency_ms < 0:
        raise ValueError("latency_ms must be non-negative")
    if cost_source not in {"vendor_reported", "catalog_estimate", "unknown"}:
        raise ValueError("invalid cost_source")
    row = await (await conn.execute(
        """insert into vendor_usage_events
                (user_id, account_id, reservation_id, vendor, service, operation, model,
                 request_id, status, units, cost, cost_source, metadata, latency_ms, error_code)
             values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb,
                     %s, %s::jsonb, %s, %s)
             on conflict (vendor, request_id) where request_id is not null do nothing
             returning id""",
        (user_id, account_id, reservation_id, vendor, service, operation, model,
         request_id, status, _json(units), _json(cost), cost_source, _json(metadata), latency_ms,
         error_code))).fetchone()
    return None if row is None else row[0]


async def settle(conn, reservation_id: int, *, actual_minor: int) -> bool:
    if actual_minor < 0:
        raise ValueError("actual_minor must be non-negative")
    row = await (await conn.execute(
        """update vendor_usage_reservations set state = 'settled', actual_minor = %s,
                    settled_at = now()
             where id = %s and state = 'held' returning id""",
        (actual_minor, reservation_id))).fetchone()
    return row is not None


async def release(conn, reservation_id: int) -> bool:
    row = await (await conn.execute(
        """update vendor_usage_reservations set state = 'released', released_at = now()
             where id = %s and state = 'held' returning id""", (reservation_id,))).fetchone()
    return row is not None


async def expire_holds(conn) -> int:
    """Sweep abandoned holds; they remain auditable as ``expired`` rows."""
    cur = await conn.execute(
        """update vendor_usage_reservations set state = 'expired'
             where state = 'held' and expires_at <= now()""")
    return cur.rowcount
