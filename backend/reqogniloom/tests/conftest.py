"""Shared fixtures for the ``reqogniloom`` app tests.

ADR-010 makes ``/health/ready`` (and therefore the ``/health/`` alias)
fail-closed on five mandatory dependencies: ``database``, ``memory_backend``,
``cache``, ``celery_worker`` and ``celery_beat``. The test suite runs against a
real PostgreSQL test database but has no live Redis/Celery broker, so the three
network-backed ``admin_ops.health_rest`` probes are pinned healthy here. The
``database`` and ``memory_backend`` probes run against the real test database.

Tests that exercise a *failing* dependency re-patch the relevant probe
explicitly (or stub ``reqogniloom.health._run_required_checks`` wholesale).
"""
from __future__ import annotations

from typing import Iterator

import pytest


@pytest.fixture(autouse=True)
def _healthy_required_infra(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Pin the network-backed mandatory probes to ``ok`` for HTTP tests."""
    monkeypatch.setattr(
        "admin_ops.health_rest._check_redis",
        lambda: {"name": "redis", "status": "ok", "detail": "PING ok"},
    )
    monkeypatch.setattr(
        "admin_ops.health_rest._check_celery_worker",
        lambda: {"name": "celery_worker", "status": "ok", "detail": "1 worker"},
    )
    monkeypatch.setattr(
        "admin_ops.health_rest._check_celery_beat",
        lambda: {"name": "celery_beat", "status": "ok", "detail": "heartbeat fresh"},
    )
    yield
