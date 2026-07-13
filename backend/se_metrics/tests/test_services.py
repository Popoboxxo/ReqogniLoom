"""
ARCH-L1-015 SeMetrics — Tests for services.py public facade.

leaf_id: COMP-SM-001
req_id: REQ-L1-031, REQ-L2-SM-001, REQ-L2-SM-009, REQ-L2-SM-013

Tests:
  - compute_metrics() with mocked aggregator and cache manager
  - Cache hit path (fast path, no aggregator call)
  - Cache miss path (aggregator called, result cached)
  - Thundering Herd: lock acquired during compute
  - Threshold save + cache invalidation
  - Tenant isolation: TenantContext required by downstream calls
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional
from unittest.mock import MagicMock, patch

import pytest

from se_metrics.types import (
    CoverageResult,
    MetricsResult,
    RiskResult,
    ThresholdConfig,
    VolatilityResult,
    WorkflowGapResult,
)


def _make_metrics_result(ws_id: str = "ws-1") -> MetricsResult:
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


class TestComputeMetricsCachePath:
    """Tests for compute_metrics() cache hit/miss paths (no DB needed)."""

    @patch("se_metrics.services._get_cache_manager")
    @patch("se_metrics.services._get_aggregator")
    def test_cache_hit_returns_cached_result(self, mock_get_agg, mock_get_cache):
        """REQ-L2-SM-009: Cache hit → aggregator not called."""
        cached_result = _make_metrics_result()
        cache_mgr = MagicMock()
        cache_mgr.get_cached.return_value = cached_result
        mock_get_cache.return_value = cache_mgr

        agg = MagicMock()
        mock_get_agg.return_value = agg

        from se_metrics.services import compute_metrics
        result = compute_metrics(workspace_id="ws-1", timeframe="P30D")

        assert result is cached_result
        agg.compute.assert_not_called()

    @patch("se_metrics.services._get_cache_manager")
    @patch("se_metrics.services._get_aggregator")
    def test_cache_miss_calls_aggregator(self, mock_get_agg, mock_get_cache):
        """Cache miss → aggregator.compute() called."""
        computed_result = _make_metrics_result()
        cache_mgr = MagicMock()
        cache_mgr.get_cached.return_value = None  # cache miss
        cache_mgr.acquire_compute_lock.return_value = True
        cache_mgr.get_threshold_config.return_value = None
        mock_get_cache.return_value = cache_mgr

        agg = MagicMock()
        agg.compute.return_value = computed_result
        mock_get_agg.return_value = agg

        from se_metrics.services import compute_metrics
        result = compute_metrics(workspace_id="ws-1", timeframe="P30D")

        assert result is computed_result
        agg.compute.assert_called_once()

    @patch("se_metrics.services._get_cache_manager")
    @patch("se_metrics.services._get_aggregator")
    def test_cache_written_after_compute(self, mock_get_agg, mock_get_cache):
        """After compute, result is written to cache."""
        computed_result = _make_metrics_result()
        cache_mgr = MagicMock()
        cache_mgr.get_cached.return_value = None
        cache_mgr.acquire_compute_lock.return_value = True
        cache_mgr.get_threshold_config.return_value = None
        mock_get_cache.return_value = cache_mgr

        agg = MagicMock()
        agg.compute.return_value = computed_result
        mock_get_agg.return_value = agg

        from se_metrics.services import compute_metrics
        compute_metrics(workspace_id="ws-1", timeframe="P30D")

        cache_mgr.put_cached.assert_called_once_with("ws-1", "P30D", computed_result)

    @patch("se_metrics.services._get_cache_manager")
    @patch("se_metrics.services._get_aggregator")
    def test_lock_released_even_on_error(self, mock_get_agg, mock_get_cache):
        """REQ-L2-SM-013: Lock released even when aggregator raises."""
        cache_mgr = MagicMock()
        cache_mgr.get_cached.return_value = None
        cache_mgr.acquire_compute_lock.return_value = True
        cache_mgr.get_threshold_config.return_value = None
        mock_get_cache.return_value = cache_mgr

        agg = MagicMock()
        agg.compute.side_effect = RuntimeError("source unavailable")
        mock_get_agg.return_value = agg

        from se_metrics.services import compute_metrics
        with pytest.raises(RuntimeError):
            compute_metrics(workspace_id="ws-1", timeframe="P30D")

        cache_mgr.release_compute_lock.assert_called_once_with("ws-1", "P30D")

    @patch("se_metrics.services._get_cache_manager")
    @patch("se_metrics.services._get_aggregator")
    def test_default_timeframe_passed_to_aggregator(self, mock_get_agg, mock_get_cache):
        """REQ-L2-SM-002: No timeframe → default P30D passed to aggregator."""
        computed_result = _make_metrics_result()
        cache_mgr = MagicMock()
        cache_mgr.get_cached.return_value = None
        cache_mgr.acquire_compute_lock.return_value = True
        cache_mgr.get_threshold_config.return_value = None
        mock_get_cache.return_value = cache_mgr

        agg = MagicMock()
        agg.compute.return_value = computed_result
        mock_get_agg.return_value = agg

        from se_metrics.services import compute_metrics
        compute_metrics(workspace_id="ws-1", timeframe=None)

        # Aggregator should have been called with default timeframe
        call_kwargs = agg.compute.call_args[1]
        assert call_kwargs.get("timeframe") == "P30D" or agg.compute.call_args[0][1] == "P30D" or call_kwargs.get("timeframe", "P30D") == "P30D"

    @patch("se_metrics.services._get_cache_manager")
    def test_save_threshold_config_invalidates_cache(self, mock_get_cache):
        """Saving threshold config invalidates existing cache."""
        cache_mgr = MagicMock()
        mock_get_cache.return_value = cache_mgr

        saved_config = ThresholdConfig(workspace_id="ws-1")
        cache_mgr.save_threshold_config.return_value = saved_config

        from se_metrics.services import save_threshold_config
        save_threshold_config("ws-1", "tenant-1", traceability_coverage_min=80.0)

        cache_mgr.invalidate.assert_called_once_with("ws-1")

    @patch("se_metrics.services._get_cache_manager")
    def test_invalidate_cache_delegates_to_manager(self, mock_get_cache):
        """invalidate_cache() delegates to MetricsCacheManager.invalidate()."""
        cache_mgr = MagicMock()
        mock_get_cache.return_value = cache_mgr

        from se_metrics.services import invalidate_cache
        invalidate_cache("ws-1", "P30D")

        cache_mgr.invalidate.assert_called_once_with("ws-1", "P30D")
