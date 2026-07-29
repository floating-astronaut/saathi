"""Privacy-hardened tracing via logfire SDK.

Local export always points at the on-box OTel Collector on localhost:4317.
Cloud export to Pydantic Logfire happens only when LOGFIRE_TOKEN is present;
the token owns the destination project (currently `indofolk-ai`).

Privacy rules (the non-negotiable ones — §13 health-adjacent PII):
  * inspect_arguments=False — hard-disable automatic function-argument capture.
    Without this, `handle_message(text="my father takes metformin...")` would
    write user message text into a span attribute.
  * Manual spans only, through the helpers in this module.
  * A fixed allow-list of attributes. Never message text, transcript, names,
    phone numbers, medicine names, or query parameters.

Failure contract (same as metrics.py):
  * Publishing must not raise. A collector outage, a full disk, or a Jaeger
    restart must not stop a reminder going out. Delivering the dose beats
    recording that we delivered it.
  * Initialisation is best-effort: if SAATHI_TRACING_ENABLED is unset, the
    module is a quiet no-op.
"""
from __future__ import annotations

import os
import logging
from contextlib import nullcontext
from typing import Any

from .config import settings

log = logging.getLogger("saathi.observability")

# ── allowed span attributes ─────────────────────────────────────────────
# Everything else is dropped by _scrub().  This is the privacy boundary.
_ALLOWED_ATTRS: frozenset[str] = frozenset({
    "kind",           # e.g. "pipeline", "safety", "agent_loop", "tool_call", "model_call"
    "latency_ms",     # wall-clock duration
    "input_tokens",   # total input tokens for a model call
    "output_tokens",  # total output tokens for a model call
    "tool_name",      # the tool the agent invoked
    "hop_count",      # which hop within the agent loop
    "model_id",       # e.g. "zai.glm-5"
    "error_class",    # exception class name when a span fails
    "trigger",        # safety classifier trigger enum value
})

# ── initialisation ──────────────────────────────────────────────────────

_tracing_enabled: bool = False
_logfire: Any = None


def _is_enabled() -> bool:
    return os.environ.get("SAATHI_TRACING_ENABLED", "").lower() in ("1", "true", "yes")


def init() -> None:
    """Best-effort initialisation.  Must never raise into a turn."""
    global _tracing_enabled, _logfire
    if not _is_enabled():
        log.info("tracing disabled — SAATHI_TRACING_ENABLED not set")
        return
    try:
        import logfire as _lf

        # Keep a local collector export even when Logfire cloud is enabled.
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
            OTLPSpanExporter,
        )

        local_exporter = OTLPSpanExporter(
            endpoint="http://localhost:4317", insecure=True
        )

        _lf.configure(
            inspect_arguments=False,   # ← the privacy hard-line
            service_name="saathi",
            service_version=settings.saathi_env or "0.1.0",
            send_to_logfire="if-token-present",
            additional_span_processors=[BatchSpanProcessor(local_exporter)],
        )

        _logfire = _lf
        _tracing_enabled = True
        if os.environ.get("LOGFIRE_TOKEN"):
            log.info("tracing enabled — Logfire cloud + local OTLP")
        else:
            log.info("tracing enabled — local OTLP only")
    except Exception:
        log.exception("tracing initialisation failed — continuing without spans")
        _tracing_enabled = False


def _scrub(attributes: dict[str, Any]) -> dict[str, Any]:
    """Drop every attribute not on the explicit allow-list."""
    return {k: v for k, v in attributes.items() if k in _ALLOWED_ATTRS}


# ── public helpers ──────────────────────────────────────────────────────

def span(name: str, **attrs: Any):
    """Create a manual span with scrubbed attributes.

    Usage:
        with observability.span("safety.classify", kind="safety"):
            result = classify(msg)
        # span closes automatically.
    """
    if not _tracing_enabled or _logfire is None:
        return nullcontext()
    clean = _scrub(attrs)
    try:
        cm = _logfire.span(name, **clean)
    except Exception:
        # Never let tracing setup take down the product.
        return nullcontext()
    return _SafeSpan(cm)


class _SafeSpan:
    """Context manager wrapper that preserves application exceptions.

    logfire span creation/enter/exit can fail if the exporter or SDK is unhappy.
    The work inside the span is the product; its exception semantics must remain
    exactly the same whether tracing is healthy, broken, or disabled.
    """

    def __init__(self, cm: Any):
        self._cm = cm
        self._entered = False

    def __enter__(self):
        try:
            self._cm.__enter__()
            self._entered = True
        except Exception:
            self._entered = False
        return self

    def __exit__(self, exc_type, exc, tb):
        if not self._entered:
            return False
        try:
            self._cm.__exit__(exc_type, exc, tb)
        except Exception:
            if exc_type is not None:
                return False
            log.exception("tracing span close failed — continuing")
        return False


def record(name: str, **attrs: Any) -> None:
    """Record a one-shot event (not a span — a point-in-time log).

    Useful for things like "tracing_init_failed" or "collector_unreachable"
    that aren't spans around work.
    """
    if not _tracing_enabled or _logfire is None:
        return
    clean = _scrub(attrs)
    try:
        _logfire.info(name, **clean)
    except Exception:
        pass


def is_enabled() -> bool:
    return _tracing_enabled
