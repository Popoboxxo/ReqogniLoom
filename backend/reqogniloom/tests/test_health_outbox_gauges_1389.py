"""Issue #1389: ``/health/ready`` must expose the outbox queue gauges.

The poll log is change-only: an idle cycle repeats the previous observation and
is reported at DEBUG, so a constant or stuck outbox backlog would be invisible
after the first cycle. The poller therefore writes the backlog and the DLQ depth
to cache-backed gauges and this endpoint publishes them as
``advisory.outbox_pending`` / ``advisory.outbox_dlq``.

These tests pin the three load-bearing properties:

* an operator can read both numbers from ``/health/ready`` — no DB query, the
  gauges come from the cache the poller already fills;
* a missing/expired gauge reads as ``"unknown"``, never as a fake zero;
* the gauges are ADVISORY: a non-zero backlog or DLQ alone never changes the
  HTTP status, and a broken gauge degrades to a warning string instead of
  crashing readiness.
"""
from __future__ import annotations

import pytest
from django.core.cache import cache
from django.test import Client

from application import event_bus_metrics

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _clean_gauges() -> None:
    """Start and end every test with no gauge written (fresh cache state)."""
    keys = (
        event_bus_metrics.OUTBOX_BACKLOG_KEY,
        event_bus_metrics.OUTBOX_DLQ_KEY,
    )
    for key in keys:
        cache.delete(key)
    yield
    for key in keys:
        cache.delete(key)


def _ready(monkeypatch: pytest.MonkeyPatch):
    """GET /health/ready with the mandatory probes stubbed as healthy.

    Only the dependency probes are stubbed — the advisory block under test runs
    for real, and so does the cache gauge read (LocMem in tests, no live Redis).
    """
    from reqogniloom import health

    monkeypatch.setattr(
        health,
        "_run_required_checks",
        lambda: {name: "ok" for name in health._REQUIRED_CHECK_NAMES},
    )
    # Keeps the advisory path DB-free for the parts this test does not cover.
    monkeypatch.setattr(health, "_embedding_dimension_mismatches", lambda: [])
    return Client().get("/health/ready")


def test_readiness_exposes_the_gauge_values(monkeypatch) -> None:
    """The poller's numbers are readable on the readiness payload."""
    event_bus_metrics.record_queue_depths(9, 1)

    response = _ready(monkeypatch)

    assert response.status_code == 200
    advisory = response.json()["advisory"]
    assert advisory["outbox_pending"] == "9"
    assert advisory["outbox_dlq"] == "1"


def test_a_nonzero_gauge_stays_advisory(monkeypatch) -> None:
    """A non-zero backlog/DLQ must not change the status code or warn."""
    event_bus_metrics.record_queue_depths(250, 4)

    response = _ready(monkeypatch)

    assert response.status_code == 200
    body = response.json()
    assert body["advisory"]["outbox_pending"] == "250"
    assert body["advisory"]["outbox_dlq"] == "4"
    assert body["status"] != "degraded"
    assert not any("outbox_pending" in item for item in body["warnings"])
    assert not any("outbox_dlq" in item for item in body["warnings"])


def test_an_unwritten_gauge_reads_as_unknown(monkeypatch) -> None:
    """No gauge (expired poller / cleared cache) is "unknown", not "0"."""
    response = _ready(monkeypatch)

    assert response.status_code == 200
    advisory = response.json()["advisory"]
    assert advisory["outbox_pending"] == "unknown"
    assert advisory["outbox_dlq"] == "unknown"


def test_readiness_never_crashes_on_a_broken_gauge(monkeypatch) -> None:
    """A cache outage degrades to a warning string, never to a 500."""
    def _boom() -> tuple[int | None, int | None]:
        raise RuntimeError("cache exploded")

    monkeypatch.setattr(event_bus_metrics, "queue_depths", _boom)

    response = _ready(monkeypatch)

    assert response.status_code == 200
    body = response.json()
    assert "outbox queue gauges unavailable" in body["warnings"]
    assert "outbox_pending" not in body["advisory"]
    assert "outbox_dlq" not in body["advisory"]
