"""Shared seams for legacy pipeline fakes.

Most older pipeline tests intentionally implement only the SQL they need.  PR-15
adds PostgreSQL advisory-lock/result semantics, which those fakes cannot emulate;
the dedicated ``test_rate_limit`` module covers that database contract directly.
Keep the existing suites focused on their own path rather than making a missing
fake row look like a production rate-limit success.
"""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _legacy_pipeline_rate_limit(monkeypatch, request):
    if request.module.__name__.endswith("test_rate_limit"):
        return

    from saathi import rate_limit

    async def reserve(*_args, **_kwargs):
        return True

    async def no_notice(*_args, **_kwargs):
        return False

    monkeypatch.setattr(rate_limit, "reserve", reserve)
    monkeypatch.setattr(rate_limit, "claim_notice", no_notice)
