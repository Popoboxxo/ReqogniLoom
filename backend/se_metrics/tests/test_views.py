"""
ARCH-L1-015 SeMetrics — Tests for DRF views (COMP-SM-001).

leaf_id: COMP-SM-001
req_id: REQ-L1-031, REQ-L2-SM-001, REQ-L2-SM-002, REQ-L2-SM-007, REQ-L2-SM-010, REQ-L2-SM-012

Tests:
  - 401 without Authorization header (REQ-L2-SM-001)
  - 400 on invalid timeframe (REQ-L2-SM-002)
  - 200 with valid request + all 8 mandatory fields (REQ-L2-SM-012)
  - PUT thresholds 200 (REQ-L2-SM-007)
  - PUT thresholds 400 on invalid type (REQ-L2-SM-007)
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional
from unittest.mock import MagicMock, patch

import pytest
from django.test import RequestFactory
from rest_framework.test import APIRequestFactory

from se_metrics.types import (
    CoverageResult,
    MetricsResult,
    RiskResult,
    ThresholdConfig,
    VolatilityResult,
    WorkflowGapResult,
)
from se_metrics.views import WorkspaceMetricsView, WorkspaceThresholdView


def _make_metrics_result(ws_id: str = "ws-1") -> MetricsResult:
    return MetricsResult(
        workspace_id=ws_id,
        computed_at=datetime.now(tz=timezone.utc),
        timeframe="P30D",
        volatility=VolatilityResult(
            total_changes=10, total_requirements=5, avg_changes_per_req=2.0
        ),
        traceability_coverage=CoverageResult(
            total=20, covered=15, coverage_percent=75.0, uncovered_ids=["r1"]
        ),
        workflow_gaps=WorkflowGapResult(total_incomplete=2),
        open_risks=RiskResult(
            total=3,
            by_severity={"critical": 1, "high": 1, "medium": 1, "low": 0},
        ),
        warnings=[],
    )


@pytest.fixture
def api_factory():
    return APIRequestFactory()


class TestWorkspaceMetricsView:
    """Tests for GET /metrics/workspace/{workspace_id}."""

    def test_returns_401_without_auth_header(self, api_factory):
        """REQ-L2-SM-001: No Authorization header → 401."""
        ws_id = str(uuid.uuid4())
        request = api_factory.get(f"/metrics/workspace/{ws_id}/")
        # No Authorization header

        view = WorkspaceMetricsView.as_view()
        response = view(request, workspace_id=ws_id)
        assert response.status_code == 401

    def test_returns_400_on_invalid_timeframe(self, api_factory):
        """REQ-L2-SM-002: Invalid timeframe → 400 with error message."""
        ws_id = str(uuid.uuid4())
        request = api_factory.get(
            f"/metrics/workspace/{ws_id}/?timeframe=INVALID",
            HTTP_AUTHORIZATION="Bearer test-token",
        )

        view = WorkspaceMetricsView.as_view()
        response = view(request, workspace_id=ws_id)
        assert response.status_code == 400
        # Check error message
        data = response.data
        assert "Invalid timeframe format" in str(data.get("error", ""))

    @patch("se_metrics.views.compute_metrics")
    def test_returns_200_with_valid_request(self, mock_compute, api_factory):
        """REQ-L2-SM-001 + REQ-L2-SM-012: Valid request → 200 with all mandatory fields."""
        ws_id = str(uuid.uuid4())
        mock_compute.return_value = _make_metrics_result(ws_id)

        request = api_factory.get(
            f"/metrics/workspace/{ws_id}/",
            HTTP_AUTHORIZATION="Bearer test-token",
        )

        view = WorkspaceMetricsView.as_view()
        response = view(request, workspace_id=ws_id)
        assert response.status_code == 200

        data = response.data
        # REQ-L2-SM-012: all 8 mandatory fields present
        required = [
            "workspace_id",
            "computed_at",
            "timeframe",
            "volatility",
            "traceability_coverage",
            "workflow_gaps",
            "open_risks",
            "warnings",
        ]
        for field in required:
            assert field in data, f"Missing required field: {field}"

    @patch("se_metrics.views.compute_metrics")
    def test_accepts_valid_timeframe_parameter(self, mock_compute, api_factory):
        """REQ-L2-SM-002: Valid P7D timeframe accepted."""
        ws_id = str(uuid.uuid4())
        mock_compute.return_value = _make_metrics_result(ws_id)

        request = api_factory.get(
            f"/metrics/workspace/{ws_id}/?timeframe=P7D",
            HTTP_AUTHORIZATION="Bearer test-token",
        )

        view = WorkspaceMetricsView.as_view()
        response = view(request, workspace_id=ws_id)
        assert response.status_code == 200
        # Timeframe should be passed to compute_metrics
        mock_compute.assert_called_once()
        call_kwargs = mock_compute.call_args[1]
        assert call_kwargs.get("timeframe") == "P7D"

    @patch("se_metrics.views.compute_metrics")
    def test_none_timeframe_uses_default(self, mock_compute, api_factory):
        """REQ-L2-SM-002: No timeframe param → None passed (service applies default)."""
        ws_id = str(uuid.uuid4())
        mock_compute.return_value = _make_metrics_result(ws_id)

        request = api_factory.get(
            f"/metrics/workspace/{ws_id}/",
            HTTP_AUTHORIZATION="Bearer test-token",
        )

        view = WorkspaceMetricsView.as_view()
        response = view(request, workspace_id=ws_id)
        assert response.status_code == 200

        call_kwargs = mock_compute.call_args[1]
        assert call_kwargs.get("timeframe") is None  # service applies default

    def test_returns_400_on_invalid_workspace_id(self, api_factory):
        """Invalid UUID workspace_id format → 400."""
        request = api_factory.get(
            "/metrics/workspace/not-a-uuid/",
            HTTP_AUTHORIZATION="Bearer test-token",
        )

        view = WorkspaceMetricsView.as_view()
        response = view(request, workspace_id="not-a-uuid")
        assert response.status_code == 400


class TestWorkspaceThresholdView:
    """Tests for GET/PUT /metrics/workspace/{workspace_id}/thresholds."""

    def test_get_returns_401_without_auth(self, api_factory):
        """GET without auth → 401."""
        ws_id = str(uuid.uuid4())
        request = api_factory.get(f"/metrics/workspace/{ws_id}/thresholds/")
        view = WorkspaceThresholdView.as_view()
        response = view(request, workspace_id=ws_id)
        assert response.status_code == 401

    def test_put_returns_401_without_auth(self, api_factory):
        """PUT without auth → 401."""
        ws_id = str(uuid.uuid4())
        request = api_factory.put(
            f"/metrics/workspace/{ws_id}/thresholds/",
            data={"traceability_coverage_min": 80.0},
            format="json",
        )
        view = WorkspaceThresholdView.as_view()
        response = view(request, workspace_id=ws_id)
        assert response.status_code == 401

    @patch("se_metrics.views.get_threshold_config")
    def test_get_returns_empty_thresholds_when_not_configured(
        self, mock_get_config, api_factory
    ):
        """GET with no config → 200 with empty thresholds."""
        mock_get_config.return_value = None
        ws_id = str(uuid.uuid4())
        request = api_factory.get(
            f"/metrics/workspace/{ws_id}/thresholds/",
            HTTP_AUTHORIZATION="Bearer test-token",
        )

        view = WorkspaceThresholdView.as_view()
        response = view(request, workspace_id=ws_id)
        assert response.status_code == 200
        assert "thresholds" in response.data

    @patch("se_metrics.views.save_threshold_config")
    def test_put_valid_thresholds_returns_200(self, mock_save, api_factory):
        """REQ-L2-SM-007: PUT with valid config → 200."""
        ws_id = str(uuid.uuid4())
        mock_save.return_value = ThresholdConfig(
            workspace_id=ws_id,
            traceability_coverage_min=80.0,
        )
        request = api_factory.put(
            f"/metrics/workspace/{ws_id}/thresholds/",
            data={"traceability_coverage_min": 80.0},
            format="json",
            HTTP_AUTHORIZATION="Bearer test-token",
        )

        view = WorkspaceThresholdView.as_view()
        response = view(request, workspace_id=ws_id)
        assert response.status_code == 200

    @patch("se_metrics.views.save_threshold_config")
    def test_put_invalid_threshold_type_returns_400(self, mock_save, api_factory):
        """REQ-L2-SM-007: PUT with non-numeric threshold → 400."""
        ws_id = str(uuid.uuid4())
        request = api_factory.put(
            f"/metrics/workspace/{ws_id}/thresholds/",
            data={"traceability_coverage_min": "not-a-number"},
            format="json",
            HTTP_AUTHORIZATION="Bearer test-token",
        )

        view = WorkspaceThresholdView.as_view()
        response = view(request, workspace_id=ws_id)
        assert response.status_code == 400
        mock_save.assert_not_called()
