"""
Tests for the celery-beat heartbeat liveness mechanism (issue #822).

The heartbeat replaces the old, always-``unknown`` ``celery_beat`` health row
that only counted ``PeriodicTask`` rows (misleading under the
``DatabaseScheduler`` + static ``CELERY_BEAT_SCHEDULE``). Beat runs a
scheduled task which writes an epoch timestamp into the shared cache; the
health check reads it back and classifies the age.

No live Redis/Celery is required: ``settings_test`` forces LocMemCache and the
heartbeat module is exercised directly against it.
"""
from __future__ import annotations

import time
from unittest.mock import patch

import pytest
from django.core.cache import cache

from admin_ops import celery_beat_heartbeat as hb
from admin_ops.health_rest import STATUS_DOWN, STATUS_OK, STATUS_UNKNOWN


@pytest.fixture(autouse=True)
def _clear_heartbeat() -> None:
    """Isolate every test from heartbeat state written by another test."""
    cache.delete(hb.HEARTBEAT_CACHE_KEY)
    yield
    cache.delete(hb.HEARTBEAT_CACHE_KEY)


class TestHeartbeatStore:
    """The pure record/read round-trip against Django's default cache."""

    def test_read_returns_none_when_absent(self) -> None:
        assert hb.read_heartbeat_timestamp() is None

    def test_record_then_read_roundtrip(self) -> None:
        before = time.time()
        hb.record_heartbeat()
        after = time.time()

        recorded = hb.read_heartbeat_timestamp()
        assert recorded is not None
        assert before <= recorded <= after

    def test_recorded_heartbeat_never_expires(self) -> None:
        """A stopped beat must keep reading as "down", never collapse to "unknown".

        Issue #822 acceptance reserves ``unknown`` for "no heartbeat has ever
        been recorded" (or an unreadable cache). If the cached value had any
        finite TTL, a beat that stopped for longer than that TTL would lose its
        key and be misreported as ``unknown`` with the factually wrong "beat has
        not started since deploy" wording. The value is therefore stored with
        ``timeout=None`` (never expires).
        """
        with patch("admin_ops.celery_beat_heartbeat.cache") as mock_cache:
            hb.record_heartbeat()

        assert mock_cache.set.call_args.kwargs["timeout"] is None


class TestSharedTask:
    """The beat-scheduled task writes the heartbeat and never raises."""

    def test_task_records_heartbeat(self) -> None:
        from admin_ops.tasks import record_celery_beat_heartbeat

        record_celery_beat_heartbeat()

        assert hb.read_heartbeat_timestamp() is not None

    def test_task_swallows_cache_errors(self) -> None:
        """A cache outage must not crash the beat loop."""
        from admin_ops.tasks import record_celery_beat_heartbeat

        with patch("admin_ops.tasks.record_heartbeat") as record:
            record.side_effect = OSError("cache down")
            record_celery_beat_heartbeat()  # must not raise

        record.assert_called_once()


class TestCheckCeleryBeat:
    """``_check_celery_beat`` classifies fresh / stale / never-seen / error."""

    def test_fresh_heartbeat_is_ok(self) -> None:
        from admin_ops.health_rest import _check_celery_beat

        hb.record_heartbeat()

        result = _check_celery_beat()

        assert result["name"] == "celery_beat"
        assert result["status"] == STATUS_OK
        assert "interval" in result["detail"]

    def test_stale_heartbeat_is_down(self) -> None:
        from admin_ops.health_rest import _check_celery_beat

        stale_ts = time.time() - (hb.HEARTBEAT_STALE_AFTER_SECONDS + 60)
        cache.set(hb.HEARTBEAT_CACHE_KEY, stale_ts, timeout=3600)

        result = _check_celery_beat()

        assert result["status"] == STATUS_DOWN
        assert "stale" in result["detail"]
        assert str(hb.HEARTBEAT_STALE_AFTER_SECONDS) in result["detail"]

    def test_never_seen_is_unknown_with_deploy_wording(self) -> None:
        from admin_ops.health_rest import _check_celery_beat

        result = _check_celery_beat()

        assert result["status"] == STATUS_UNKNOWN
        assert "not started since deploy" in result["detail"]

    def test_store_read_error_is_unknown_and_does_not_raise(self) -> None:
        from admin_ops.health_rest import _check_celery_beat

        with patch("admin_ops.celery_beat_heartbeat.cache") as mock_cache:
            mock_cache.get.side_effect = OSError("cache down")
            result = _check_celery_beat()

        assert result["status"] == STATUS_UNKNOWN
        assert "cache down" in result["detail"]
