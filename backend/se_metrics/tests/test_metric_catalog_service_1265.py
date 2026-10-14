"""
ARCH-L1-015 SeMetrics — Tests for the registry service facade (Issue #1265).

leaf_id: COMP-SM-001
req_id: REQ-L1-031, REQ-L2-SM-001

``get_metric_catalog`` is pure metadata; ``get_metric_values`` wraps the
existing cached ``compute_metrics``. Both are exercised with ``compute_metrics``
/ ``invalidate_cache`` patched, so no DB is required.
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

from se_metrics.registry import ALL_METRIC_KEYS, DEFAULT_METRIC_KEYS
from se_metrics.services import get_metric_catalog, get_metric_values
from se_metrics.types import (
    CoverageResult,
    MetricsResult,
    RiskResult,
    VerificationCoverageResult,
    VolatilityResult,
    WorkflowGapResult,
)


def _result() -> MetricsResult:
    return MetricsResult(
        workspace_id="22222222-2222-2222-2222-222222222222",
        computed_at=datetime(2026, 10, 14, 9, 30, tzinfo=timezone.utc),
        timeframe="P30D",
        volatility=VolatilityResult(
            total_changes=20, total_requirements=10, avg_changes_per_req=2.0
        ),
        traceability_coverage=CoverageResult(
            total=20, covered=15, coverage_percent=75.0
        ),
        workflow_gaps=WorkflowGapResult(total_incomplete=3),
        open_risks=RiskResult(
            total=4, by_severity={"critical": 1, "high": 2, "medium": 1, "low": 0}
        ),
        verification_coverage=VerificationCoverageResult(
            total=10, covered=8, coverage_percent=80.0
        ),
        warnings=[],
    )


class TestGetMetricCatalog:
    def test_returns_registry_metadata_without_touching_the_db(self) -> None:
        payload = get_metric_catalog()
        assert [entry["key"] for entry in payload["metrics"]] == list(ALL_METRIC_KEYS)
        assert payload["default_keys"] == list(DEFAULT_METRIC_KEYS)
        assert payload["all_keys"] == list(ALL_METRIC_KEYS)


class TestGetMetricValues:
    @patch("se_metrics.services.invalidate_cache")
    @patch("se_metrics.services.compute_metrics")
    def test_omitted_keys_return_every_registered_metric(
        self, mock_compute, mock_invalidate
    ) -> None:
        mock_compute.return_value = _result()

        payload = get_metric_values(workspace_id="ws-1")

        assert set(payload["metrics"]) == set(ALL_METRIC_KEYS)
        assert payload["unknown_keys"] == []
        assert payload["workspace_id"] == "22222222-2222-2222-2222-222222222222"
        assert payload["timeframe"] == "P30D"
        assert payload["computed_at"] == "2026-10-14T09:30:00+00:00"
        mock_invalidate.assert_not_called()

    @patch("se_metrics.services.invalidate_cache")
    @patch("se_metrics.services.compute_metrics")
    def test_selected_keys_carry_metadata_and_the_scalar(
        self, mock_compute, mock_invalidate
    ) -> None:
        mock_compute.return_value = _result()

        payload = get_metric_values(workspace_id="ws-1", keys=["open_risks_critical"])

        assert list(payload["metrics"]) == ["open_risks_critical"]
        entry = payload["metrics"]["open_risks_critical"]
        assert entry["value"] == 1
        assert entry["unit"] == ""
        assert entry["scope"] == "workspace"
        assert entry["expensive"] is False
        assert entry["computed_at"] == payload["computed_at"]
        assert entry["title_key"] == "metrics.catalog.open_risks_critical.title"

    @patch("se_metrics.services.invalidate_cache")
    @patch("se_metrics.services.compute_metrics")
    def test_unknown_keys_are_reported_alongside_the_known_values(
        self, mock_compute, mock_invalidate
    ) -> None:
        mock_compute.return_value = _result()

        payload = get_metric_values(
            workspace_id="ws-1", keys=["verification_coverage", "nope"]
        )

        assert list(payload["metrics"]) == ["verification_coverage"]
        assert payload["metrics"]["verification_coverage"]["value"] == 80.0
        assert payload["unknown_keys"] == ["nope"]

    @patch("se_metrics.services.invalidate_cache")
    @patch("se_metrics.services.compute_metrics")
    def test_timeframe_is_forwarded(self, mock_compute, mock_invalidate) -> None:
        mock_compute.return_value = _result()

        get_metric_values(workspace_id="ws-1", timeframe="P7D")

        assert mock_compute.call_args.kwargs["timeframe"] == "P7D"

    @patch("se_metrics.services.invalidate_cache")
    @patch("se_metrics.services.compute_metrics")
    def test_refresh_invalidates_the_cache_before_reading(
        self, mock_compute, mock_invalidate
    ) -> None:
        mock_compute.return_value = _result()

        get_metric_values(workspace_id="ws-1", timeframe="P7D", refresh=True)

        mock_invalidate.assert_called_once_with("ws-1", "P7D")
        mock_compute.assert_called_once()

    @patch("se_metrics.services.invalidate_cache")
    @patch("se_metrics.services.compute_metrics")
    def test_a_plain_read_never_invalidates(self, mock_compute, mock_invalidate) -> None:
        mock_compute.return_value = _result()

        get_metric_values(workspace_id="ws-1", refresh=False)

        mock_invalidate.assert_not_called()
