"""Telemetry that must never take the worker down with it.

A missed cardiac dose is this product's worst failure, and until now it would
have been invisible: `scheduling.sweep_stuck` records a stranded turn, but
nothing told a human. This is the half that tells a human.

Two rules, and they pull in opposite directions:

  * **Publishing must not raise.** A CloudWatch outage, an expired credential or
    a throttle must not stop a reminder going out. Delivering the dose beats
    recording that we delivered it.
  * **Silence must still be loud.** The alarm on `WorkerHeartbeat` is configured
    `treat_missing_data: breaching`, so if this module stops publishing — for
    any reason, including its own failure — the alarm fires. That means a
    metrics outage pages someone about a worker that is actually fine.

That false alarm is the deliberate choice. The alternative is an alarm that goes
quiet when the monitoring breaks, which is indistinguishable from healthy and is
exactly how a dead worker stays unnoticed for a week.
"""
from __future__ import annotations

import logging

import boto3
from botocore.config import Config

from .config import settings

log = logging.getLogger("saathi.metrics")

#: The IAM grant is scoped to this namespace by condition, so a typo here is an
#: AccessDenied rather than a metric quietly landing somewhere unmonitored.
NAMESPACE = "Saathi"

_client = None


def _cw():
    global _client
    if _client is None:
        # Short timeouts and no retries: this sits in the worker's tick. Being
        # slow here delays reminders, which is worse than losing a datapoint.
        _client = boto3.client(
            "cloudwatch",
            region_name=settings.bedrock_region,
            config=Config(connect_timeout=3, read_timeout=5,
                          retries={"max_attempts": 1}),
        )
    return _client


def emit(name: str, value: float = 1.0, unit: str = "Count") -> bool:
    """Publish one datapoint. Returns whether it landed; never raises.

    The return value exists so callers can log or test, not so they can retry —
    retrying inside the tick is how a metrics outage becomes a reminder outage.
    """
    try:
        _cw().put_metric_data(
            Namespace=NAMESPACE,
            MetricData=[{"MetricName": name, "Value": float(value), "Unit": unit}],
        )
        return True
    except Exception:  # noqa: BLE001 - telemetry never breaks the caller
        # ERROR, not WARNING: this failing means the heartbeat alarm is about to
        # fire for the wrong reason, and whoever is paged needs this line.
        log.exception("metric %r not published — heartbeat alarm may now be lying", name)
        return False
