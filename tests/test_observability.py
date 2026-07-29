"""Tests for saathi.observability — privacy-hardened tracing module.

Covers the three non-negotiables from the plan:
  1. inspect_arguments=False — no automatic arg capture
  2. Allow-list scrub — PII attributes are dropped
  3. Disabled by default — no side effects when SAATHI_TRACING_ENABLED is unset
  4. Cloud export only when LOGFIRE_TOKEN exists; local export remains wired
"""
from __future__ import annotations

import importlib
import os
from pathlib import Path

import pytest


class FakeLogfire:
    """Minimal fake of logfire for testing the public API shape."""

    def __init__(self):
        self.spans: list[tuple[str, dict]] = []
        self.records: list[tuple[str, dict]] = []

    def configure(self, **kwargs):
        assert kwargs.get("inspect_arguments") is False, (
            "inspect_arguments must be False — auto arg capture leaks PII"
        )
        assert kwargs.get("send_to_logfire") == "if-token-present", (
            "cloud export must depend on LOGFIRE_TOKEN, not unconditional sending"
        )
        assert kwargs.get("additional_span_processors"), (
            "local collector export must remain wired alongside Logfire cloud"
        )

    def span(self, name, **attrs):
        self.spans.append((name, attrs))
        return _FakeSpanContext()

    def info(self, name, **attrs):
        self.records.append((name, attrs))


class _FakeSpanContext:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


class _FailingExitSpan:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        raise RuntimeError("tracing close failed")


@pytest.fixture(autouse=True)
def reset_observability(monkeypatch):
    """Every test starts with a clean module state."""
    monkeypatch.delenv("SAATHI_TRACING_ENABLED", raising=False)
    monkeypatch.delenv("LOGFIRE_TOKEN", raising=False)
    obs = importlib.import_module("saathi.observability")
    obs._tracing_enabled = False
    obs._logfire = None
    yield
    obs._tracing_enabled = False
    obs._logfire = None


# ── disabled-by-default ──────────────────────────────────────────────────


def test_disabled_by_default():
    """With no env var set, the module is a no-op."""
    obs = importlib.import_module("saathi.observability")
    assert obs.is_enabled() is False


def test_span_noop_when_disabled():
    """span() does nothing when tracing is off."""
    obs = importlib.import_module("saathi.observability")
    with obs.span("test_span", kind="test"):
        pass  # must not raise


def test_record_noop_when_disabled():
    """record() does nothing when tracing is off."""
    obs = importlib.import_module("saathi.observability")
    obs.record("some_event", kind="test")  # must not raise


# ── allow-list scrubbing ─────────────────────────────────────────────────


def test_scrub_allows_listed_attrs():
    """Attributes on the allow-list survive scrubbing."""
    obs = importlib.import_module("saathi.observability")
    attrs = {
        "kind": "agent_loop",
        "latency_ms": 142,
        "input_tokens": 300,
        "output_tokens": 50,
        "tool_name": "lookup",
        "hop_count": 2,
        "model_id": "zai.glm-5",
        "error_class": "ValueError",
        "trigger": "medical_emergency",
    }
    result = obs._scrub(attrs)
    assert result == attrs


def test_scrub_drops_pii():
    """Message text, names, transcripts and other PII are dropped."""
    obs = importlib.import_module("saathi.observability")
    attrs = {
        "kind": "agent_loop",
        "latency_ms": 142,
        "user_text": "my father takes metformin 500mg daily",
        "transcript": "mera naam Ramesh hai",
        "contact_name": "Ramesh Kumar",
        "medicine_name": "metformin",
        "query_params": "q=diabetes+symptoms",
        "phone": "+918071581944",
    }
    result = obs._scrub(attrs)
    assert "kind" in result
    assert "latency_ms" in result
    assert "user_text" not in result
    assert "transcript" not in result
    assert "contact_name" not in result
    assert "medicine_name" not in result
    assert "query_params" not in result
    assert "phone" not in result


def test_scrub_unknown_attrs_dropped():
    """Any attribute not on the allow-list is silently removed."""
    obs = importlib.import_module("saathi.observability")
    result = obs._scrub({"random_field": "something", "kind": "test"})
    assert result == {"kind": "test"}


def test_scrub_empty():
    obs = importlib.import_module("saathi.observability")
    assert obs._scrub({}) == {}


# ── init respects privacy flags ──────────────────────────────────────────


def test_init_disabled_when_no_env():
    """init() is a no-op when SAATHI_TRACING_ENABLED is not set."""
    obs = importlib.import_module("saathi.observability")
    obs.init()
    assert obs.is_enabled() is False
    assert obs._logfire is None


def test_init_with_env_var(monkeypatch):
    """With SAATHI_TRACING_ENABLED, init wires logfire with local OTLP.

    This test uses a realistic path: it sets the env var, imports logfire
    (which exists on the box via uv), and verifies configure() is called
    with the right arguments.
    """
    monkeypatch.setenv("SAATHI_TRACING_ENABLED", "1")

    import logfire as real_logfire

    obs = importlib.import_module("saathi.observability")

    # Capture what logfire.configure() is called with
    calls = []

    def fake_configure(**kwargs):
        calls.append(kwargs)

    monkeypatch.setattr(real_logfire, "configure", fake_configure)

    obs.init()

    # inspect_arguments=False is the hard privacy line
    assert len(calls) > 0, "logfire.configure() was not called"
    assert calls[0].get("inspect_arguments") is False, (
        "inspect_arguments MUST be False — auto arg capture leaks user message text"
    )
    assert calls[0].get("send_to_logfire") == "if-token-present", (
        "Logfire cloud export must require LOGFIRE_TOKEN"
    )
    assert calls[0].get("additional_span_processors"), (
        "local OTel Collector export must not be removed"
    )


def test_init_with_logfire_token_still_keeps_privacy_and_local_export(monkeypatch):
    """The project token may enable cloud export, but not argument capture."""
    monkeypatch.setenv("SAATHI_TRACING_ENABLED", "1")
    monkeypatch.setenv("LOGFIRE_TOKEN", "test-token")

    import logfire as real_logfire

    obs = importlib.import_module("saathi.observability")
    calls = []

    def fake_configure(**kwargs):
        calls.append(kwargs)

    monkeypatch.setattr(real_logfire, "configure", fake_configure)

    obs.init()

    assert calls[0]["send_to_logfire"] == "if-token-present"
    assert calls[0]["inspect_arguments"] is False
    assert calls[0]["additional_span_processors"]


# ── span context manager ─────────────────────────────────────────────────


def test_span_noop_when_import_fails(monkeypatch):
    """If logfire import fails, span degrades gracefully."""
    monkeypatch.setenv("SAATHI_TRACING_ENABLED", "1")

    obs = importlib.import_module("saathi.observability")

    def _fail(*a, **kw):
        raise ImportError("logfire not available")

    monkeypatch.setattr("saathi.observability.init", _fail)

    with obs.span("should_not_raise", kind="test"):
        pass


def test_span_preserves_application_exception():
    """Tracing must not replace or suppress the turn's real exception."""
    obs = importlib.import_module("saathi.observability")
    fake = FakeLogfire()
    obs._logfire = fake
    obs._tracing_enabled = True

    with pytest.raises(ValueError, match="real app error"):
        with obs.span("test_span", kind="test"):
            raise ValueError("real app error")


def test_span_close_failure_does_not_break_successful_work():
    """Exporter/SDK close errors degrade to no-op behavior."""
    obs = importlib.import_module("saathi.observability")
    fake = FakeLogfire()
    fake.span = lambda name, **attrs: _FailingExitSpan()
    obs._logfire = fake
    obs._tracing_enabled = True

    with obs.span("test_span", kind="test"):
        pass


def test_tracing_stack_ports_do_not_conflict():
    """Collector receives on 4317; Jaeger receives from collector on 4318."""
    root = Path(__file__).resolve().parents[1]
    setup = (root / "ops" / "setup-tracing.sh").read_text()
    jaeger = (root / "ops" / "saathi-jaeger.service").read_text()

    assert "endpoint: 127.0.0.1:4317" in setup
    assert "endpoint: 127.0.0.1:4318" in setup
    assert "--collector.otlp.grpc.host-port=127.0.0.1:4318" in jaeger
    assert "--collector.otlp.grpc.host-port=0.0.0.0:4317" not in jaeger


# ── observability module is importable at module level ───────────────────


def test_observability_imports():
    """The module must be importable without side effects.

    This is critical: both web/app.py and worker/__main__.py import it
    at module level, and the import itself must not call init().
    """
    import saathi.observability as obs

    # Import must not enable tracing automatically
    assert obs.is_enabled() is False
