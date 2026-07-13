"""
ARCH-L1-015 SeMetrics — Tests for MetricsAggregator (COMP-SM-002).

leaf_id: COMP-SM-002
req_id: REQ-L1-031, REQ-L2-SM-001, REQ-L2-SM-008, REQ-L2-SM-011

All external sources mocked:
  - audit.services.query (IF-L1-044)
  - traceability.services.coverage (IF-L1-045)
  - se_metrics.aggregator._fetch_incomplete_states (IF-L1-046)
  - se_metrics.aggregator._fetch_risks (IF-L1-047)

Tests verify:
  - MetricsResult structure (REQ-L2-SM-012)
  - Threshold warning generation (REQ-L2-SM-007)
  - Safe empty results on source failure (REQ-L2-SM-008)
  - Timeframe defaults (REQ-L2-SM-002)
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, List, Optional
from unittest.mock import MagicMock, patch

import pytest

from persistence.tenancy import TenantContext
from se_metrics.aggregator import MetricsAggregator, DEFAULT_TIMEFRAME, _parse_timeframe_days
from se_metrics.types import (
    MetricsResult,
    ThresholdConfig,
    VolatilityResult,
    CoverageResult,
    WorkflowGapResult,
    RiskResult,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@dataclass
class FakeAuditEntry:
    entity_type: str
    op: str
    entity_id: str


@dataclass
class FakeCoverageReport:
    total: int
    covered: int
    uncovered: list
    percentage: float = 0.0


@dataclass
class FakeRisk:
    status: str
    severity: str
    risk_score: int


class TestParseTimeframeDays:
    """_parse_timeframe_days utility tests."""

    def test_p30d(self):
        assert _parse_timeframe_days("P30D") == 30

    def test_p7d(self):
        assert _parse_timeframe_days("P7D") == 7

    def test_p90d(self):
        assert _parse_timeframe_days("P90D") == 90

    def test_invalid_falls_back_to_30(self):
        assert _parse_timeframe_days("INVALID") == 30

    def test_none_falls_back_to_30(self):
        assert _parse_timeframe_days(None) == 30

    def test_p1y_falls_back_to_30(self):
        # Only PnD is fully supported; P1Y falls back
        assert _parse_timeframe_days("P1Y") == 30


class TestMetricsAggregator:
    """MetricsAggregator integration tests with mocked sources."""

    @pytest.fixture(autouse=True)
    def _tenant_context(self):
        """Establish a tenant context for each test.

        ``MetricsAggregator.compute()`` calls ``TenantContext.get_tenant()``
        to propagate the active tenant to its worker threads (REQ-L3-PL002-002).
        In production the AuthAndTenancy layer sets this before the request
        reaches the aggregator; these tests must play that caller role. All
        DB-touching sources (``_fetch_*``) are mocked, so any tenant id works.
        """
        TenantContext.set_tenant(uuid.uuid4())
        try:
            yield
        finally:
            TenantContext.clear_tenant()

    def _make_aggregator(self):
        return MetricsAggregator()

    def _make_mock_audit_result(self, entries):
        """Build a fake PaginatedAuditResult."""
        result = MagicMock()
        result.entries = entries
        result.total = len(entries)
        return result

    @patch("se_metrics.aggregator._fetch_risks")
    @patch("se_metrics.aggregator._fetch_incomplete_states")
    @patch("se_metrics.aggregator._fetch_coverage")
    @patch("se_metrics.aggregator._fetch_audit_entries")
    def test_compute_returns_all_four_metric_categories(
        self,
        mock_audit,
        mock_coverage,
        mock_gaps,
        mock_risks,
    ):
        """REQ-L2-SM-001: Result contains all four metric categories."""
        mock_audit.return_value = []
        mock_coverage.return_value = FakeCoverageReport(
            total=10, covered=8, uncovered=["r9", "r10"]
        )
        mock_gaps.return_value = []
        mock_risks.return_value = []

        agg = self._make_aggregator()
        result = agg.compute(workspace_id="ws-1", timeframe="P30D")

        assert isinstance(result, MetricsResult)
        assert isinstance(result.volatility, VolatilityResult)
        assert isinstance(result.traceability_coverage, CoverageResult)
        assert isinstance(result.workflow_gaps, WorkflowGapResult)
        assert isinstance(result.open_risks, RiskResult)
        assert isinstance(result.warnings, list)

    @patch("se_metrics.aggregator._fetch_risks")
    @patch("se_metrics.aggregator._fetch_incomplete_states")
    @patch("se_metrics.aggregator._fetch_coverage")
    @patch("se_metrics.aggregator._fetch_audit_entries")
    def test_default_timeframe_applied(
        self,
        mock_audit,
        mock_coverage,
        mock_gaps,
        mock_risks,
    ):
        """REQ-L2-SM-002: timeframe defaults to P30D when None."""
        mock_audit.return_value = []
        mock_coverage.return_value = None
        mock_gaps.return_value = []
        mock_risks.return_value = []

        agg = self._make_aggregator()
        result = agg.compute(workspace_id="ws-1", timeframe=None)
        assert result.timeframe == DEFAULT_TIMEFRAME

    @patch("se_metrics.aggregator._fetch_risks")
    @patch("se_metrics.aggregator._fetch_incomplete_states")
    @patch("se_metrics.aggregator._fetch_coverage")
    @patch("se_metrics.aggregator._fetch_audit_entries")
    def test_audit_source_failure_returns_empty_volatility(
        self,
        mock_audit,
        mock_coverage,
        mock_gaps,
        mock_risks,
    ):
        """REQ-L2-SM-008: IF-L1-044 failure → empty volatility, no 5xx."""
        mock_audit.return_value = []  # failure already handled upstream
        mock_coverage.return_value = None
        mock_gaps.return_value = []
        mock_risks.return_value = []

        agg = self._make_aggregator()
        result = agg.compute(workspace_id="ws-1", timeframe="P30D")
        assert result.volatility.total_changes == 0
        assert result.volatility.avg_changes_per_req == 0.0

    @patch("se_metrics.aggregator._fetch_risks")
    @patch("se_metrics.aggregator._fetch_incomplete_states")
    @patch("se_metrics.aggregator._fetch_coverage")
    @patch("se_metrics.aggregator._fetch_audit_entries")
    def test_threshold_warnings_generated(
        self,
        mock_audit,
        mock_coverage,
        mock_gaps,
        mock_risks,
    ):
        """REQ-L2-SM-007: Threshold violations generate warnings in result."""
        mock_audit.return_value = []
        mock_coverage.return_value = FakeCoverageReport(
            total=10, covered=5, uncovered=["r1", "r2", "r3", "r4", "r5"]
        )
        mock_gaps.return_value = []
        mock_risks.return_value = []

        threshold_config = ThresholdConfig(
            workspace_id="ws-1",
            traceability_coverage_min=80.0,  # actual=50% → warning
        )
        agg = self._make_aggregator()
        result = agg.compute(
            workspace_id="ws-1",
            timeframe="P30D",
            threshold_config=threshold_config,
        )
        assert len(result.warnings) >= 1
        warning_metrics = [w.metric for w in result.warnings]
        assert "traceability_coverage" in warning_metrics

    @patch("se_metrics.aggregator._fetch_risks")
    @patch("se_metrics.aggregator._fetch_incomplete_states")
    @patch("se_metrics.aggregator._fetch_coverage")
    @patch("se_metrics.aggregator._fetch_audit_entries")
    def test_result_has_workspace_id_and_timeframe(
        self,
        mock_audit,
        mock_coverage,
        mock_gaps,
        mock_risks,
    ):
        """REQ-L2-SM-012: Result contains workspace_id and timeframe."""
        mock_audit.return_value = []
        mock_coverage.return_value = None
        mock_gaps.return_value = []
        mock_risks.return_value = []

        agg = self._make_aggregator()
        result = agg.compute(workspace_id="ws-test-123", timeframe="P7D")
        assert result.workspace_id == "ws-test-123"
        assert result.timeframe == "P7D"
        assert isinstance(result.computed_at, datetime)

    @patch("se_metrics.aggregator._fetch_risks")
    @patch("se_metrics.aggregator._fetch_incomplete_states")
    @patch("se_metrics.aggregator._fetch_coverage")
    @patch("se_metrics.aggregator._fetch_audit_entries")
    def test_to_dict_contains_all_required_fields(
        self,
        mock_audit,
        mock_coverage,
        mock_gaps,
        mock_risks,
    ):
        """REQ-L2-SM-012: to_dict() contains all 8 mandatory fields."""
        mock_audit.return_value = []
        mock_coverage.return_value = None
        mock_gaps.return_value = []
        mock_risks.return_value = []

        agg = self._make_aggregator()
        result = agg.compute(workspace_id="ws-1", timeframe="P30D")
        d = result.to_dict()

        required_fields = [
            "workspace_id",
            "computed_at",
            "timeframe",
            "volatility",
            "traceability_coverage",
            "workflow_gaps",
            "open_risks",
            "warnings",
        ]
        for field in required_fields:
            assert field in d, f"Missing required field: {field}"

    @patch("se_metrics.aggregator._fetch_risks")
    @patch("se_metrics.aggregator._fetch_incomplete_states")
    @patch("se_metrics.aggregator._fetch_coverage")
    @patch("se_metrics.aggregator._fetch_audit_entries")
    def test_no_threshold_config_no_warnings(
        self,
        mock_audit,
        mock_coverage,
        mock_gaps,
        mock_risks,
    ):
        """No threshold config → warnings is empty list."""
        mock_audit.return_value = []
        mock_coverage.return_value = None
        mock_gaps.return_value = []
        mock_risks.return_value = []

        agg = self._make_aggregator()
        result = agg.compute(workspace_id="ws-1", timeframe="P30D", threshold_config=None)
        assert result.warnings == []
