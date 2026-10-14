"""Regression tests for MetricsViewSet (issue #12).

GET /api/v1/metrics/?workspace_id=<uuid> used to return 200 with null-valued
metrics for a workspace UUID that doesn't exist. It must 404 instead.
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

from rest_framework.test import APIRequestFactory

from application.base import NotFoundError
from rest_api.metrics_views import MetricsViewSet


def _metrics_request(params: dict | None = None):
    from auth_tenancy.context import AuthContext, AuthMethod

    factory = APIRequestFactory()
    url = "/api/v1/metrics/"
    if params:
        query_string = "&".join(f"{k}={v}" for k, v in params.items())
        req = factory.get(f"{url}?{query_string}")
    else:
        req = factory.get(url)
    req.auth_context = AuthContext(
        user_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        active_roles=("admin",),
        auth_method=AuthMethod.BEARER_TOKEN,
    )
    return req


def test_list_returns_404_for_nonexistent_workspace() -> None:
    req = _metrics_request(params={"workspace_id": str(uuid.uuid4())})
    view = MetricsViewSet.as_view({"get": "list"})
    with patch(
        "rest_api.metrics_views.WorkspaceService.get_workspace",
        side_effect=NotFoundError("not found"),
    ):
        response = view(req)
    assert response.status_code == 404


def test_list_returns_200_for_existing_workspace() -> None:
    req = _metrics_request(params={"workspace_id": str(uuid.uuid4())})
    view = MetricsViewSet.as_view({"get": "list"})
    result = MagicMock()
    result.to_dict.return_value = {"coverage": {}}
    with patch(
        "rest_api.metrics_views.WorkspaceService.get_workspace",
        return_value=MagicMock(),
    ), patch("rest_api.metrics_views.compute_metrics", return_value=result):
        response = view(req)
    assert response.status_code == 200


def test_list_returns_400_for_malformed_workspace_id() -> None:
    req = _metrics_request(params={"workspace_id": "not-a-uuid"})
    view = MetricsViewSet.as_view({"get": "list"})
    response = view(req)
    assert response.status_code == 400


def test_list_returns_400_without_workspace_id() -> None:
    req = _metrics_request()
    view = MetricsViewSet.as_view({"get": "list"})
    response = view(req)
    assert response.status_code == 400


class TestTenantContextHygiene:
    """SA-38 (SYSTEMAUDIT_2026-08-27 §4.3 F-09): ``TenantContext.set_tenant()``
    at the top of ``list()`` used to have no matching ``clear_tenant()`` in a
    ``finally`` — every early-return path (missing/malformed workspace_id,
    404) left the thread-local armed for whatever request the pool worker
    thread serves next. All four response paths below must leave the
    thread-local context cleared.
    """

    def _assert_cleared(self) -> None:
        from persistence.tenancy import TenantContext

        assert not TenantContext.is_set(), (
            "TenantContext leaked past MetricsViewSet.list() — a pooled "
            "worker thread would carry this tenant into the next request."
        )

    def test_context_cleared_after_missing_workspace_id(self) -> None:
        req = _metrics_request()
        view = MetricsViewSet.as_view({"get": "list"})
        view(req)
        self._assert_cleared()

    def test_context_cleared_after_malformed_workspace_id(self) -> None:
        req = _metrics_request(params={"workspace_id": "not-a-uuid"})
        view = MetricsViewSet.as_view({"get": "list"})
        view(req)
        self._assert_cleared()

    def test_context_cleared_after_workspace_not_found(self) -> None:
        req = _metrics_request(params={"workspace_id": str(uuid.uuid4())})
        view = MetricsViewSet.as_view({"get": "list"})
        with patch(
            "rest_api.metrics_views.WorkspaceService.get_workspace",
            side_effect=NotFoundError("not found"),
        ):
            view(req)
        self._assert_cleared()

    def test_context_cleared_after_success(self) -> None:
        req = _metrics_request(params={"workspace_id": str(uuid.uuid4())})
        view = MetricsViewSet.as_view({"get": "list"})
        result = MagicMock()
        result.to_dict.return_value = {"coverage": {}}
        with patch(
            "rest_api.metrics_views.WorkspaceService.get_workspace",
            return_value=MagicMock(),
        ), patch("rest_api.metrics_views.compute_metrics", return_value=result):
            view(req)
        self._assert_cleared()

    def test_context_cleared_after_unhandled_exception(self) -> None:
        req = _metrics_request(params={"workspace_id": str(uuid.uuid4())})
        view = MetricsViewSet.as_view({"get": "list"})
        with patch(
            "rest_api.metrics_views.WorkspaceService.get_workspace",
            return_value=MagicMock(),
        ), patch(
            "rest_api.metrics_views.compute_metrics",
            side_effect=RuntimeError("boom"),
        ):
            response = view(req)
        assert response.status_code == 500
        self._assert_cleared()


# ---------------------------------------------------------------------------
# Issue #1265 — central statistics catalogue + values-by-keys
# ---------------------------------------------------------------------------


class TestMetricCatalogEndpoint:
    """``GET /api/v1/metrics/catalog/`` (Issue #1265)."""

    def _catalog_request(self):
        from rest_api.metrics_views import MetricsViewSet

        return MetricsViewSet.as_view({"get": "catalog"})

    def test_catalog_returns_the_registry_metadata(self) -> None:
        req = _metrics_request()
        view = self._catalog_request()

        response = view(req)

        assert response.status_code == 200
        keys = [entry["key"] for entry in response.data["metrics"]]
        assert "traceability_coverage" in keys
        assert "verification_coverage" in keys
        assert response.data["default_keys"]
        assert response.data["all_keys"] == keys

    def test_catalog_requires_authentication(self) -> None:
        from rest_framework.test import APIRequestFactory

        req = APIRequestFactory().get("/api/v1/metrics/catalog/")
        response = self._catalog_request()(req)

        assert response.status_code == 401


class TestMetricValuesByKeys:
    """``GET /api/v1/metrics/?keys=…`` (Issue #1265)."""

    def test_keys_parameter_returns_the_values_envelope(self) -> None:
        req = _metrics_request(
            params={"workspace_id": str(uuid.uuid4()), "keys": "open_risks"}
        )
        view = MetricsViewSet.as_view({"get": "list"})
        envelope = {
            "workspace_id": "ws",
            "computed_at": "2026-10-14T09:30:00+00:00",
            "timeframe": "P30D",
            "metrics": {"open_risks": {"key": "open_risks", "value": 4}},
            "unknown_keys": [],
        }
        with patch(
            "rest_api.metrics_views.WorkspaceService.get_workspace",
            return_value=MagicMock(),
        ), patch(
            "rest_api.metrics_views.get_metric_values", return_value=envelope
        ) as mock_values:
            response = view(req)

        assert response.status_code == 200
        assert response.data == envelope
        assert mock_values.call_args.kwargs["keys"] == ["open_risks"]
        assert mock_values.call_args.kwargs["refresh"] is False

    def test_refresh_parameter_is_forwarded(self) -> None:
        req = _metrics_request(
            params={
                "workspace_id": str(uuid.uuid4()),
                "keys": "open_risks",
                "refresh": "true",
            }
        )
        view = MetricsViewSet.as_view({"get": "list"})
        with patch(
            "rest_api.metrics_views.WorkspaceService.get_workspace",
            return_value=MagicMock(),
        ), patch(
            "rest_api.metrics_views.get_metric_values", return_value={}
        ) as mock_values:
            view(req)

        assert mock_values.call_args.kwargs["refresh"] is True

    def test_plain_read_without_keys_keeps_the_full_result_shape(self) -> None:
        """Additive: the keys envelope is opt-in, so old clients are unaffected."""
        req = _metrics_request(params={"workspace_id": str(uuid.uuid4())})
        view = MetricsViewSet.as_view({"get": "list"})
        result = MagicMock()
        result.to_dict.return_value = {"volatility": {}, "warnings": []}
        with patch(
            "rest_api.metrics_views.WorkspaceService.get_workspace",
            return_value=MagicMock(),
        ), patch(
            "rest_api.metrics_views.compute_metrics", return_value=result
        ), patch(
            "rest_api.metrics_views.get_metric_values"
        ) as mock_values:
            response = view(req)

        assert response.status_code == 200
        assert response.data == {"volatility": {}, "warnings": []}
        mock_values.assert_not_called()

    def test_refresh_without_keys_invalidates_before_computing(self) -> None:
        req = _metrics_request(
            params={"workspace_id": str(uuid.uuid4()), "refresh": "true"}
        )
        view = MetricsViewSet.as_view({"get": "list"})
        result = MagicMock()
        result.to_dict.return_value = {}
        with patch(
            "rest_api.metrics_views.WorkspaceService.get_workspace",
            return_value=MagicMock(),
        ), patch(
            "rest_api.metrics_views.compute_metrics", return_value=result
        ), patch("rest_api.metrics_views.invalidate_cache") as mock_invalidate:
            view(req)

        mock_invalidate.assert_called_once()

    def test_keys_path_still_404s_for_an_unknown_workspace(self) -> None:
        req = _metrics_request(
            params={"workspace_id": str(uuid.uuid4()), "keys": "open_risks"}
        )
        view = MetricsViewSet.as_view({"get": "list"})
        with patch(
            "rest_api.metrics_views.WorkspaceService.get_workspace",
            side_effect=NotFoundError("not found"),
        ):
            response = view(req)

        assert response.status_code == 404
