"""
ARCH-L1-015 SeMetrics — Tests for MetricsCacheManager (COMP-SM-008).

leaf_id: COMP-SM-008
req_id: REQ-L1-031, REQ-L2-SM-007, REQ-L2-SM-009, REQ-L2-SM-013

Tests:
  - Cache read/write cycle
  - TTL expiry (stale cache returns None)
  - Cache failure fallback (no exception raised)
  - Threshold config CRUD
  - Thundering Herd Prevention lock acquire/release
  - Cache invalidation
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional
from unittest.mock import MagicMock, patch

import pytest

from se_metrics.cache import MetricsCacheManager
from se_metrics.types import (
    CoverageResult,
    MetricsResult,
    RiskResult,
    ThresholdConfig,
    ThresholdWarning,
    VolatileRequirement,
    VolatilityResult,
    WorkflowGapResult,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_metrics_result(workspace_id: str = "ws-1", timeframe: str = "P30D") -> MetricsResult:
    """Build a minimal MetricsResult fixture."""
    return MetricsResult(
        workspace_id=workspace_id,
        computed_at=datetime.now(tz=timezone.utc),
        timeframe=timeframe,
        volatility=VolatilityResult(
            total_changes=10, total_requirements=5, avg_changes_per_req=2.0
        ),
        traceability_coverage=CoverageResult(
            total=20, covered=15, coverage_percent=75.0, uncovered_ids=["r1"]
        ),
        workflow_gaps=WorkflowGapResult(total_incomplete=2),
        open_risks=RiskResult(
            total=3, by_severity={"critical": 1, "high": 1, "medium": 1, "low": 0}
        ),
        warnings=[],
    )


class TestMetricsCacheManagerDeserialization:
    """Test cache serialization/deserialization roundtrip (no DB required)."""

    def test_roundtrip_serialize_deserialize(self):
        """MetricsResult → to_dict() → _deserialize() → same data."""
        mgr = MetricsCacheManager()
        original = _make_metrics_result()
        result_json = original.to_dict()
        restored = mgr._deserialize(result_json)

        assert restored is not None
        assert restored.workspace_id == original.workspace_id
        assert restored.timeframe == original.timeframe
        assert restored.volatility.total_changes == original.volatility.total_changes
        assert (
            restored.traceability_coverage.coverage_percent
            == original.traceability_coverage.coverage_percent
        )
        assert restored.workflow_gaps.total_incomplete == original.workflow_gaps.total_incomplete
        assert restored.open_risks.total == original.open_risks.total
        assert restored.open_risks.by_severity == original.open_risks.by_severity

    def test_deserialize_bad_json_returns_none(self):
        """_deserialize on malformed input returns None (no exception)."""
        mgr = MetricsCacheManager()
        result = mgr._deserialize({"bad": "data"})
        assert result is None

    def test_roundtrip_preserves_volatile_requirement_title(self):
        """Issue #454: title must survive a cache write/read roundtrip —
        otherwise a cache hit would silently drop it even though the live
        MetricsAggregator resolves it correctly."""
        mgr = MetricsCacheManager()
        original = _make_metrics_result()
        original.volatility.top10_volatile = [
            VolatileRequirement(
                requirement_id="11111111-1111-1111-1111-111111111111",
                change_count=5,
                title="Login must support 2FA",
            )
        ]
        result_json = original.to_dict()
        restored = mgr._deserialize(result_json)

        assert restored is not None
        assert len(restored.volatility.top10_volatile) == 1
        assert restored.volatility.top10_volatile[0].title == "Login must support 2FA"
        assert (
            restored.volatility.top10_volatile[0].requirement_id
            == "11111111-1111-1111-1111-111111111111"
        )

    def test_deserialize_old_cache_entry_without_title_loads_cleanly(self):
        """Issue #454 fix rollout: cache entries written before the "title"
        field existed must still load without crashing on a warm cache
        (deploy-time compatibility) — title defaults to ""."""
        mgr = MetricsCacheManager()
        original = _make_metrics_result()
        result_json = original.to_dict()
        # Simulate a pre-existing cache entry: no "title" key at all.
        result_json["volatility"]["top10_volatile"] = [
            {"requirement_id": "22222222-2222-2222-2222-222222222222", "change_count": 2}
        ]

        restored = mgr._deserialize(result_json)

        assert restored is not None
        assert len(restored.volatility.top10_volatile) == 1
        assert restored.volatility.top10_volatile[0].title == ""
        assert restored.volatility.top10_volatile[0].change_count == 2

    def test_roundtrip_with_warnings(self):
        """Warnings survive serialization roundtrip."""
        mgr = MetricsCacheManager()
        original = _make_metrics_result()
        original.warnings = [
            ThresholdWarning(
                metric="traceability_coverage",
                actual=65.0,
                threshold=80.0,
                description="Coverage below minimum",
            )
        ]
        result_json = original.to_dict()
        restored = mgr._deserialize(result_json)

        assert restored is not None
        assert len(restored.warnings) == 1
        assert restored.warnings[0].metric == "traceability_coverage"


class TestThunderingHerdLock:
    """REQ-L2-SM-013: Thundering Herd Prevention via in-process lock."""

    def test_lock_acquire_and_release(self):
        """Lock can be acquired and released without error."""
        mgr = MetricsCacheManager()
        ws_id = str(uuid.uuid4())
        timeframe = "P30D"

        acquired = mgr.acquire_compute_lock(ws_id, timeframe, timeout_seconds=1)
        assert acquired is True
        # Lock should be released without error
        mgr.release_compute_lock(ws_id, timeframe)

    def test_second_acquire_blocked_by_first(self):
        """Second acquire on same key returns False when lock is held (timeout)."""
        import threading

        mgr = MetricsCacheManager()
        ws_id = str(uuid.uuid4())
        timeframe = "P30D"

        # Acquire first lock
        acquired1 = mgr.acquire_compute_lock(ws_id, timeframe, timeout_seconds=5)
        assert acquired1 is True

        try:
            # Second acquire should time out immediately
            acquired2 = mgr.acquire_compute_lock(ws_id, timeframe, timeout_seconds=0)
            assert acquired2 is False
        finally:
            mgr.release_compute_lock(ws_id, timeframe)

    def test_release_unheld_lock_does_not_raise(self):
        """Releasing an unheld lock logs but does not raise."""
        mgr = MetricsCacheManager()
        ws_id = str(uuid.uuid4())
        # Should not raise even if lock was never acquired
        mgr.release_compute_lock(ws_id, "P30D")


class TestMetricsCacheManagerWithDb:
    """Tests that require database access (MetricCache and ThresholdConfig models)."""

    @pytest.fixture(autouse=True)
    def _setup_tenant(self, metrics_tenant_context):
        """Provide DB access *and* an active tenant context.

        SA-35: the models are tenant-scoped now, so a query without a context
        raises ``TenantContextNotSetError`` before any SQL — the same fail-fast
        every other tenant-scoped model has.
        """
        pass

    def test_get_cached_miss_returns_none(self, db):
        """Cache miss returns None."""
        mgr = MetricsCacheManager()
        result = mgr.get_cached("nonexistent-ws", "P30D")
        assert result is None

    def test_put_and_get_cached_roundtrip(self, db):
        """put_cached then get_cached returns the same data."""
        mgr = MetricsCacheManager()
        ws_id = str(uuid.uuid4())
        original = _make_metrics_result(workspace_id=ws_id)

        mgr.put_cached(ws_id, "P30D", original, ttl_seconds=600)
        restored = mgr.get_cached(ws_id, "P30D")

        assert restored is not None
        assert restored.workspace_id == ws_id
        assert restored.volatility.total_changes == original.volatility.total_changes

    def test_stale_cache_returns_none(self, db):
        """Cached entry past TTL returns None."""
        import django.utils.timezone as dj_tz
        from se_metrics.models import MetricCache

        mgr = MetricsCacheManager()
        ws_id = str(uuid.uuid4())
        original = _make_metrics_result(workspace_id=ws_id)

        # Write entry with TTL of 0 (immediately stale)
        mgr.put_cached(ws_id, "P30D", original, ttl_seconds=0)
        result = mgr.get_cached(ws_id, "P30D")
        assert result is None

    def test_invalidate_removes_cache_entry(self, db):
        """invalidate() removes the cache entry."""
        mgr = MetricsCacheManager()
        ws_id = str(uuid.uuid4())
        original = _make_metrics_result(workspace_id=ws_id)

        mgr.put_cached(ws_id, "P30D", original)
        mgr.invalidate(ws_id)
        result = mgr.get_cached(ws_id, "P30D")
        assert result is None

    def test_invalidate_specific_timeframe(self, db):
        """invalidate(ws, timeframe) removes only the specified entry."""
        mgr = MetricsCacheManager()
        ws_id = str(uuid.uuid4())

        original_30d = _make_metrics_result(workspace_id=ws_id, timeframe="P30D")
        original_7d = _make_metrics_result(workspace_id=ws_id, timeframe="P7D")

        mgr.put_cached(ws_id, "P30D", original_30d, ttl_seconds=600)
        mgr.put_cached(ws_id, "P7D", original_7d, ttl_seconds=600)

        mgr.invalidate(ws_id, timeframe="P30D")

        assert mgr.get_cached(ws_id, "P30D") is None
        assert mgr.get_cached(ws_id, "P7D") is not None

    def test_threshold_config_not_found_returns_none(self, db):
        """No ThresholdConfig for workspace → None."""
        mgr = MetricsCacheManager()
        result = mgr.get_threshold_config(str(uuid.uuid4()))
        assert result is None

    def test_save_and_get_threshold_config(self, metrics_tenant_context):
        """save_threshold_config persists and get_threshold_config retrieves."""
        mgr = MetricsCacheManager()
        ws_id = str(uuid.uuid4())
        # SA-35: the tenant must match the active context — an arbitrary id is
        # no longer accepted (it would stamp a foreign tenant onto the row).
        tenant_id = str(metrics_tenant_context.id)

        saved = mgr.save_threshold_config(
            workspace_id=ws_id,
            tenant_id=tenant_id,
            traceability_coverage_min=80.0,
            volatility_max_avg=1.5,
            workflow_gaps_max=10,
            open_risks_max_critical=2,
        )
        assert saved.traceability_coverage_min == 80.0
        assert saved.volatility_max_avg == 1.5

        loaded = mgr.get_threshold_config(ws_id)
        assert loaded is not None
        assert loaded.traceability_coverage_min == 80.0
        assert loaded.workflow_gaps_max == 10
        assert loaded.open_risks_max_critical == 2

    def test_update_threshold_config(self, metrics_tenant_context):
        """save_threshold_config updates existing config (upsert)."""
        mgr = MetricsCacheManager()
        ws_id = str(uuid.uuid4())
        tenant_id = str(metrics_tenant_context.id)

        mgr.save_threshold_config(ws_id, tenant_id, traceability_coverage_min=70.0)
        mgr.save_threshold_config(ws_id, tenant_id, traceability_coverage_min=90.0)

        loaded = mgr.get_threshold_config(ws_id)
        assert loaded.traceability_coverage_min == 90.0
