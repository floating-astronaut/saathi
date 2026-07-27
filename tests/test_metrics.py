"""Telemetry must not be able to take the worker down.

The worker publishes a heartbeat every tick and the alarm treats missing data as
breaching. That makes this module's failure mode load-bearing in both
directions, so both directions are pinned here.
"""
import logging

from saathi import metrics


class Boom:
    def put_metric_data(self, **_kw):
        raise RuntimeError("cloudwatch is having a day")


class Recorder:
    def __init__(self): self.calls = []
    def put_metric_data(self, **kw): self.calls.append(kw)


def test_a_metrics_outage_never_raises(monkeypatch):
    """A reminder going out beats recording that it went out."""
    monkeypatch.setattr(metrics, "_cw", lambda: Boom())
    assert metrics.emit("WorkerHeartbeat") is False


def test_a_metrics_outage_is_logged_at_error(monkeypatch, caplog):
    """Whoever gets paged needs this line to know the alarm is lying."""
    monkeypatch.setattr(metrics, "_cw", lambda: Boom())
    with caplog.at_level(logging.ERROR, logger="saathi.metrics"):
        metrics.emit("WorkerHeartbeat")
    assert any(r.levelno >= logging.ERROR for r in caplog.records)


def test_emits_into_the_scoped_namespace(monkeypatch):
    """The IAM grant is conditioned on this namespace; a typo is an AccessDenied."""
    rec = Recorder()
    monkeypatch.setattr(metrics, "_cw", lambda: rec)
    assert metrics.emit("WorkerHeartbeat") is True
    assert rec.calls[0]["Namespace"] == "Saathi"
    assert rec.calls[0]["MetricData"][0]["MetricName"] == "WorkerHeartbeat"


def test_zero_is_published_not_skipped(monkeypatch):
    """A tick that dispatched nothing is still a tick. Skipping it would look
    identical to a dead worker."""
    rec = Recorder()
    monkeypatch.setattr(metrics, "_cw", lambda: rec)
    metrics.emit("TurnsDispatched", 0)
    assert rec.calls[0]["MetricData"][0]["Value"] == 0.0
