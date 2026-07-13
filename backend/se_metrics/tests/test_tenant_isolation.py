"""
ARCH-L1-015 SeMetrics — Tenant isolation tests.

leaf_id: COMP-SM-001
req_id: REQ-L1-031, REQ-L2-SM-010

Tests:
  - compute_metrics() respects TenantContext (tenant data isolation)
  - Cache entries are workspace-scoped (different workspace → different cache key)
  - ThresholdConfig is workspace-scoped
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from se_metrics.types import (
    CoverageResult,
    MetricsResult,
    RiskResult,
    VolatilityResult,
    WorkflowGapResult,
)


def _make_result(ws_id: str = "ws-1") -> MetricsResult:
    return MetricsResult(
        workspace_id=ws_id,
        computed_at=datetime.now(tz=timezone.utc),
        timeframe="P30D",
        volatility=VolatilityResult(total_changes=0, total_requirements=0, avg_changes_per_req=0.0),
        traceability_coverage=CoverageResult(total=0, covered=0, coverage_percent=0.0),
        workflow_gaps=WorkflowGapResult(total_incomplete=0),
        open_risks=RiskResult(total=0, by_severity={"critical": 0, "high": 0, "medium": 0, "low": 0}),
        warnings=[],
    )


class TestCacheTenantIsolation:
    """Tests that cache is workspace-scoped (tenant isolation, REQ-L2-SM-010)."""

    @pytest.fixture(autouse=True)
    def _db(self, db):
        pass

    def test_different_workspaces_have_independent_caches(self, db):
        """Caching for ws-A does not affect ws-B (workspace scoping)."""
        from se_metrics.cache import MetricsCacheManager

        mgr = MetricsCacheManager()
        ws_a = str(uuid.uuid4())
        ws_b = str(uuid.uuid4())

        result_a = _make_result(ws_a)
        mgr.put_cached(ws_a, "P30D", result_a, ttl_seconds=600)

        # ws-B cache should be empty
        assert mgr.get_cached(ws_b, "P30D") is None
        # ws-A cache should still be present
        assert mgr.get_cached(ws_a, "P30D") is not None

    def test_threshold_config_workspace_scoped(self, db):
        """ThresholdConfig for ws-A does not affect ws-B."""
        from se_metrics.cache import MetricsCacheManager

        mgr = MetricsCacheManager()
        ws_a = str(uuid.uuid4())
        ws_b = str(uuid.uuid4())
        tenant_id = str(uuid.uuid4())

        mgr.save_threshold_config(
            workspace_id=ws_a,
            tenant_id=tenant_id,
            traceability_coverage_min=80.0,
        )

        config_a = mgr.get_threshold_config(ws_a)
        config_b = mgr.get_threshold_config(ws_b)

        assert config_a is not None
        assert config_a.traceability_coverage_min == 80.0
        assert config_b is None

    def test_cache_invalidation_is_workspace_scoped(self, db):
        """Invalidating ws-A does not invalidate ws-B."""
        from se_metrics.cache import MetricsCacheManager

        mgr = MetricsCacheManager()
        ws_a = str(uuid.uuid4())
        ws_b = str(uuid.uuid4())

        result_a = _make_result(ws_a)
        result_b = _make_result(ws_b)

        mgr.put_cached(ws_a, "P30D", result_a, ttl_seconds=600)
        mgr.put_cached(ws_b, "P30D", result_b, ttl_seconds=600)

        mgr.invalidate(ws_a)

        assert mgr.get_cached(ws_a, "P30D") is None
        assert mgr.get_cached(ws_b, "P30D") is not None


class TestComputeMetricsTenantContext:
    """Tests for compute_metrics() with TenantContext requirements."""

    @patch("se_metrics.services._get_cache_manager")
    @patch("se_metrics.services._get_aggregator")
    def test_compute_metrics_propagates_workspace_id_to_aggregator(
        self, mock_get_agg, mock_get_cache
    ):
        """workspace_id is correctly passed to aggregator."""
        ws_id = str(uuid.uuid4())
        result = _make_result(ws_id)

        cache_mgr = MagicMock()
        cache_mgr.get_cached.return_value = None
        cache_mgr.acquire_compute_lock.return_value = True
        cache_mgr.get_threshold_config.return_value = None
        mock_get_cache.return_value = cache_mgr

        agg = MagicMock()
        agg.compute.return_value = result
        mock_get_agg.return_value = agg

        from se_metrics.services import compute_metrics
        returned = compute_metrics(workspace_id=ws_id, timeframe="P30D")

        assert returned.workspace_id == ws_id
        # Verify workspace_id was passed to aggregator
        call_kwargs = agg.compute.call_args
        assert str(ws_id) in str(call_kwargs)

    @patch("se_metrics.services._get_cache_manager")
    @patch("se_metrics.services._get_aggregator")
    def test_different_workspace_ids_produce_independent_results(
        self, mock_get_agg, mock_get_cache
    ):
        """Two different workspace_ids produce independent metric results."""
        ws_1 = str(uuid.uuid4())
        ws_2 = str(uuid.uuid4())
        result_1 = _make_result(ws_1)
        result_2 = _make_result(ws_2)

        cache_mgr = MagicMock()
        cache_mgr.get_cached.return_value = None
        cache_mgr.acquire_compute_lock.return_value = True
        cache_mgr.get_threshold_config.return_value = None
        mock_get_cache.return_value = cache_mgr

        agg = MagicMock()
        agg.compute.side_effect = [result_1, result_2]
        mock_get_agg.return_value = agg

        from se_metrics.services import compute_metrics
        r1 = compute_metrics(workspace_id=ws_1, timeframe="P30D")
        r2 = compute_metrics(workspace_id=ws_2, timeframe="P30D")

        assert r1.workspace_id == ws_1
        assert r2.workspace_id == ws_2
